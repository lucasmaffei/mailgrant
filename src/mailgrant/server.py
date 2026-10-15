"""FastAPI HTTP layer.

URL shape:
  GET    /health
  GET    /mailboxes
  GET    /inbox                                       unified across all IMAP mailboxes
         ?mailbox=name1,addr@x  ← optional filter (name or email address)
         &from=&to=&subject=&body=&text=
         &since=&before=&unseen=&seen=&flagged=&answered=
         &larger_than=&smaller_than=&folder=&limit=
  GET    /mailboxes/{name}/folders                    (IMAP)
  GET    /mailboxes/{name}/messages?folder=&limit=&search=
  GET    /mailboxes/{name}/search?from=&subject=&...  structured single-mailbox
  GET    /mailboxes/{name}/messages/{uid}?folder=
  DELETE /mailboxes/{name}/messages/{uid}?folder=&permanent=
  POST   /mailboxes/{name}/messages/{uid}/seen        body: {"seen": bool}
  POST   /mailboxes/{name}/send                       (SMTP)
  GET    /whoami                                      the caller's agent, scopes, mailboxes

Every route answers only for the mailboxes and scopes granted to the bearer
token (see grants.py). A mailbox outside the grant is a 404, a missing scope
a 403.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, AsyncIterator

from fastapi import Body, FastAPI, HTTPException, Path, Query, Request
from pydantic import BaseModel
from starlette.routing import Mount
from starlette.types import ASGIApp, Receive, Scope, Send

from . import __version__, audit
from .config import Config, ConfigError, MailboxConfig, load_config
from .grants import Forbidden, NotFound, Principal, authenticate, check_sender
from .grants import resolve as grant_resolve
from .grants import select_imap
from .imap_client import ImapError
from .imap_client import delete_message as imap_delete
from .imap_client import fetch_message as imap_fetch
from .imap_client import list_folders as imap_list_folders
from .imap_client import list_messages as imap_list_messages
from .imap_client import mark_seen as imap_mark_seen
from .imap_client import search_messages as imap_search_messages
from .imap_client import unified_search as imap_unified_search
from .mcp_server import build_session_manager, mcp_lifespan
from .schemas import (
    FoldersResponse,
    GenericOK,
    HealthResponse,
    MailboxList,
    MailboxSummary,
    SendRequest,
)
from .smtp_client import SmtpError
from .smtp_client import send as smtp_send

log = logging.getLogger("mailgrant")


def _load_or_die() -> Config:
    try:
        return load_config()
    except ConfigError as e:
        log.error("config load failed: %s", e)
        raise


def _need(mb: MailboxConfig, proto: str) -> None:
    if getattr(mb, proto) is None:
        raise HTTPException(
            status_code=409,
            detail=f"mailbox {mb.name!r} has no {proto} configured",
        )


_AUTH_EXEMPT_PATHS = frozenset({"/health"})
_MCP_PATH = "/mcp"
_MCP_PATH_WITH_TRAILING_SLASH = f"{_MCP_PATH}/"
_MCP_RAW_PATH = _MCP_PATH.encode("ascii")
_MCP_RAW_PATH_WITH_TRAILING_SLASH = _MCP_PATH_WITH_TRAILING_SLASH.encode("ascii")


def _principal_from_scope(cfg: Config, scope: Scope) -> Principal | None:
    """Resolve the bearer token to its principal. No tokens configured denies everything."""
    for k, v in scope.get("headers", []):
        if k == b"authorization":
            auth = v.decode("latin-1")
            if not auth.startswith("Bearer "):
                return None
            return authenticate(cfg, auth[7:].strip())
    return None


async def _send_401(send: Send) -> None:
    body = b'{"detail":"missing or invalid Bearer token"}'
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b"Bearer"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class _MCPSlashNormalizer:
    """Route the documented MCP path to the mounted Streamable HTTP handler."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != _MCP_PATH:
            await self._app(scope, receive, send)
            return

        normalized_scope = dict(scope)
        normalized_scope["path"] = _MCP_PATH_WITH_TRAILING_SLASH
        if scope.get("raw_path") == _MCP_RAW_PATH:
            normalized_scope["raw_path"] = _MCP_RAW_PATH_WITH_TRAILING_SLASH
        await self._app(normalized_scope, receive, send)


class _BearerASGI:
    """Pure-ASGI bearer-auth wrapper around the whole app.

    Pure ASGI (not BaseHTTPMiddleware) so it doesn't buffer streaming
    responses — required for the MCP streamable-HTTP transport mounted
    under /mcp to keep working.
    """

    def __init__(self, app: ASGIApp, cfg: Config) -> None:
        self._app = app
        self._cfg = cfg

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        # Mailboxes and agents managed from the web app may have changed in
        # another worker; this is cheap (one version check, at most per second).
        self._cfg.refresh()
        path = scope.get("path", "")
        # The web app authenticates people with passkey sessions, not bearer
        # tokens; its own router checks every /app/api call.
        web_path = self._cfg.web_enabled and (
            path == "/" or path == "/app" or path.startswith("/app/")
        )
        if path in _AUTH_EXEMPT_PATHS or web_path:
            await self._app(scope, receive, send)
            return
        principal = _principal_from_scope(self._cfg, scope)
        if principal is None:
            await _send_401(send)
            return
        # Starlette's Request.state reads scope["state"]; the MCP transport
        # gets the same Request, so both layers see who is calling.
        scope.setdefault("state", {})["principal"] = principal
        await self._app(scope, receive, send)


def create_app(config: Config | None = None) -> FastAPI:
    cfg = config or _load_or_die()
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    audit.configure(cfg.audit_log)

    web_hooks: list[tuple[Any, Any]] = []
    mcp_manager: Any = None

    @contextlib.asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        for start, _ in web_hooks:
            start()
        try:
            async with mcp_lifespan(mcp_manager):
                yield
        finally:
            for _, stop in web_hooks:
                stop()

    app = FastAPI(
        title="mailgrant",
        version=__version__,
        description="One email gateway for many AI agents, each with its own mailboxes and scopes.",
        lifespan=_lifespan,
    )

    if cfg.web_enabled:
        # Imported only here: an MCP-only instance never loads the web stack.
        from .web import mount as mount_web

        # Before the MCP server: with web.manage the mailboxes come from the
        # web app's database, and the tool list depends on them.
        web_hooks.append(mount_web(app, cfg))

    mcp_manager = build_session_manager(cfg)
    app.router.routes.append(Mount(_MCP_PATH, app=mcp_manager.handle_request))

    app.add_middleware(_MCPSlashNormalizer)
    app.add_middleware(_BearerASGI, cfg=cfg)

    @app.get("/health", response_model=HealthResponse)
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    def _who(request: Request) -> Principal:
        principal = getattr(request.state, "principal", None)
        if principal is None:  # the middleware guarantees it; belt and braces
            raise HTTPException(status_code=401, detail="missing or invalid Bearer token")
        return principal

    def _guard(
        request: Request, name: str, scope: str, action: str, **fields: Any
    ) -> MailboxConfig:
        """Resolve the mailbox and check the scope, recording the decision either way."""
        who = _who(request)
        try:
            mb = grant_resolve(cfg, who, name)
            who.require(scope)
        except NotFound as e:
            audit.record(who.name, action, "denied", mailbox=name, reason="not_found", **fields)
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Forbidden as e:
            audit.record(who.name, action, "denied", mailbox=name, reason="scope", **fields)
            raise HTTPException(status_code=403, detail=str(e)) from e
        return mb

    @app.get("/whoami")
    def whoami(request: Request) -> dict[str, Any]:
        who = _who(request)
        return {
            "agent": who.name,
            "scopes": sorted(who.scopes),
            "mailboxes": [m.name for m in who.visible(cfg)],
            "all_mailboxes": who.mailboxes is None,
        }

    @app.get("/mailboxes", response_model=MailboxList)
    def list_mailboxes(request: Request) -> MailboxList:
        who = _who(request)
        return MailboxList(
            mailboxes=[
                MailboxSummary(
                    name=m.name,
                    description=m.description,
                    imap=m.imap is not None,
                    smtp=m.smtp is not None,
                )
                for m in who.visible(cfg)
            ]
        )

    # ── Unified inbox (default view) ────────────────────────────────────────

    @app.get("/inbox")
    def inbox(
        request: Request,
        mailbox: str | None = Query(None, description="CSV of mailbox names or addresses"),
        folder: str | None = Query(None),
        limit: int = Query(50, ge=1, le=500),
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        subject: str | None = Query(None),
        body: str | None = Query(None),
        text: str | None = Query(None),
        since: str | None = Query(None, description="IMAP date e.g. 1-Jan-2026"),
        before: str | None = Query(None),
        unseen: bool | None = Query(None),
        seen: bool | None = Query(None),
        flagged: bool | None = Query(None),
        answered: bool | None = Query(None),
        larger_than: int | None = Query(None, ge=0),
        smaller_than: int | None = Query(None, ge=0),
    ) -> dict[str, Any]:
        who = _who(request)
        try:
            who.require("read")
            targets = select_imap(cfg, who, mailbox)
        except Forbidden as e:
            audit.record(who.name, "inbox", "denied", reason="scope")
            raise HTTPException(status_code=403, detail=str(e)) from e
        except NotFound as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        audit.record(who.name, "inbox", mailboxes=[m.name for m in targets])
        return imap_unified_search(
            targets,
            folder=folder,
            limit=limit,
            from_=from_,
            to=to,
            subject=subject,
            body=body,
            text=text,
            since=since,
            before=before,
            unseen=unseen,
            seen=seen,
            flagged=flagged,
            answered=answered,
            larger_than=larger_than,
            smaller_than=smaller_than,
        )

    # ── IMAP ────────────────────────────────────────────────────────────────

    @app.get("/mailboxes/{name}/folders", response_model=FoldersResponse)
    def folders(request: Request, name: str = Path(...)) -> FoldersResponse:
        mb = _guard(request, name, "read", "list_folders")
        _need(mb, "imap")
        try:
            return FoldersResponse(folders=imap_list_folders(mb.imap))  # type: ignore[arg-type]
        except ImapError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    @app.get("/mailboxes/{name}/messages")
    def list_msgs(
        request: Request,
        name: str = Path(...),
        folder: str | None = Query(None),
        limit: int = Query(50, ge=1, le=500),
        search: str = Query("ALL"),
    ) -> dict[str, Any]:
        mb = _guard(request, name, "read", "list_messages", folder=folder)
        _need(mb, "imap")
        try:
            msgs = imap_list_messages(
                mb.imap,  # type: ignore[arg-type]
                folder=folder,
                limit=limit,
                search=search,
            )
            return {"messages": msgs}
        except ImapError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    @app.get("/mailboxes/{name}/search")
    def search_msgs(
        request: Request,
        name: str = Path(...),
        folder: str | None = Query(None),
        limit: int = Query(50, ge=1, le=500),
        from_: str | None = Query(None, alias="from"),
        to: str | None = Query(None),
        subject: str | None = Query(None),
        body: str | None = Query(None),
        text: str | None = Query(None),
        since: str | None = Query(None),
        before: str | None = Query(None),
        unseen: bool | None = Query(None),
        seen: bool | None = Query(None),
        flagged: bool | None = Query(None),
        answered: bool | None = Query(None),
        larger_than: int | None = Query(None, ge=0),
        smaller_than: int | None = Query(None, ge=0),
    ) -> dict[str, Any]:
        mb = _guard(request, name, "read", "search", folder=folder)
        _need(mb, "imap")
        try:
            msgs = imap_search_messages(
                mb.imap,  # type: ignore[arg-type]
                folder=folder,
                limit=limit,
                from_=from_,
                to=to,
                subject=subject,
                body=body,
                text=text,
                since=since,
                before=before,
                unseen=unseen,
                seen=seen,
                flagged=flagged,
                answered=answered,
                larger_than=larger_than,
                smaller_than=smaller_than,
            )
            return {"messages": msgs}
        except ImapError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    @app.get("/mailboxes/{name}/messages/{uid}")
    def get_msg(
        request: Request,
        name: str = Path(...),
        uid: str = Path(...),
        folder: str | None = Query(None),
        reader: bool = Query(
            False, description="Add `body_reader`: readable text/markdown from HTML"
        ),
    ) -> dict[str, Any]:
        mb = _guard(request, name, "read", "get_message", uid=uid, folder=folder)
        _need(mb, "imap")
        audit.record(_who(request).name, "get_message", mailbox=mb.name, uid=uid, folder=folder)
        try:
            return imap_fetch(mb.imap, uid, folder=folder, reader=reader)  # type: ignore[arg-type]
        except ImapError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    @app.delete("/mailboxes/{name}/messages/{uid}")
    def del_msg(
        request: Request,
        name: str = Path(...),
        uid: str = Path(...),
        folder: str | None = Query(None),
        permanent: bool = Query(False, description="Erase instead of moving to the trash"),
    ) -> dict[str, Any]:
        mb = _guard(request, name, "delete", "delete_message", uid=uid, folder=folder)
        _need(mb, "imap")
        who = _who(request).name
        try:
            result = imap_delete(
                mb.imap, uid, folder=folder, permanent=permanent  # type: ignore[arg-type]
            )
        except ImapError as e:
            audit.record(who, "delete_message", "error", mailbox=mb.name, uid=uid, error=str(e))
            raise HTTPException(status_code=502, detail=str(e)) from e
        audit.record(
            who,
            "delete_message",
            mailbox=mb.name,
            uid=uid,
            folder=folder,
            moved_to=result.get("moved_to"),
            erased=result.get("erased"),
        )
        return result

    class _SeenBody(BaseModel):
        seen: bool = True

    @app.post("/mailboxes/{name}/messages/{uid}/seen", response_model=GenericOK)
    def set_seen(
        request: Request,
        name: str = Path(...),
        uid: str = Path(...),
        folder: str | None = Query(None),
        body: _SeenBody = Body(default_factory=_SeenBody),
    ) -> GenericOK:
        mb = _guard(request, name, "mark", "mark_seen", uid=uid, seen=body.seen)
        _need(mb, "imap")
        audit.record(_who(request).name, "mark_seen", mailbox=mb.name, uid=uid, seen=body.seen)
        try:
            imap_mark_seen(mb.imap, uid, folder=folder, seen=body.seen)  # type: ignore[arg-type]
        except ImapError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return GenericOK()

    # ── SMTP ────────────────────────────────────────────────────────────────

    @app.post("/mailboxes/{name}/send")
    def send(
        request: Request, name: str = Path(...), req: SendRequest = Body(...)
    ) -> dict[str, Any]:
        mb = _guard(request, name, "send", "send")
        _need(mb, "smtp")
        who = _who(request).name
        rcpts = [str(x) for x in [*req.to, *(req.cc or []), *(req.bcc or [])]]
        try:
            check_sender(mb.smtp, req.from_address)  # type: ignore[arg-type]
        except Forbidden as e:
            audit.record(who, "send", "denied", mailbox=mb.name, reason="from_address")
            raise HTTPException(status_code=403, detail=str(e)) from e
        copy_to = (
            (mb.imap, mb.smtp.save_copy_to)  # type: ignore[union-attr]
            if mb.imap is not None and mb.smtp and mb.smtp.save_copy_to
            else None
        )
        try:
            result = smtp_send(
                mb.smtp,  # type: ignore[arg-type]
                to=[str(x) for x in req.to],
                subject=req.subject,
                body_text=req.body_text,
                body_html=req.body_html,
                cc=[str(x) for x in (req.cc or [])],
                bcc=[str(x) for x in (req.bcc or [])],
                from_address=req.from_address,
                reply_to=str(req.reply_to) if req.reply_to else None,
                in_reply_to=req.in_reply_to,
                references=req.references,
                copy_to=copy_to,
            )
        except SmtpError as e:
            audit.record(who, "send", "error", mailbox=mb.name, to=rcpts, error=str(e))
            raise HTTPException(status_code=502, detail=str(e)) from e
        audit.record(
            who,
            "send",
            mailbox=mb.name,
            to=rcpts,
            message_id=result.get("message_id"),
            in_reply_to=req.in_reply_to,
        )
        return result

    return app
