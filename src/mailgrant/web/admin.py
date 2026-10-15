"""Managing mailboxes and agents from the web app, under /app/api/admin.

Only mounted with `web.manage: true`. Reading is open to the signed-in
person; every change also needs a passkey check from the last few minutes
(the app asks for Face ID / Touch ID again), because these endpoints hand
out tokens and hold mailbox passwords.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from .. import audit
from ..config import ALL_MAILBOXES, Config, ImapConfig, MailboxConfig, SmtpConfig
from ..grants import Principal
from ..imap_client import ImapError
from ..imap_client import check_login as imap_check
from ..smtp_client import SmtpError
from ..smtp_client import check_login as smtp_check
from .managed import Managed, ManageError, uses


def build_admin_router(
    cfg: Config,
    managed: Managed,
    person: Callable[..., Principal],
    confirmed: Callable[[Request], None],
) -> APIRouter:
    assert cfg.web is not None
    origin = cfg.web.origin
    router = APIRouter(prefix="/admin")  # inside the /app/api router

    def fail(e: ManageError) -> HTTPException:
        return HTTPException(422, str(e))

    def mailbox_view(m: MailboxConfig) -> dict[str, Any]:
        def part(p: ImapConfig | SmtpConfig | None) -> dict[str, Any] | None:
            if p is None:
                return None
            data = p.model_dump(exclude={"password"})
            data["has_password"] = bool(p.password)
            return data

        return {
            "name": m.name,
            "description": m.description,
            "address": m.imap.username if m.imap else m.smtp.username if m.smtp else m.name,
            "imap": part(m.imap),
            "smtp": part(m.smtp),
            "agents": uses(cfg, m.name),
        }

    def agent_view(a: Any, dates: dict[str, str | None]) -> dict[str, Any]:
        return {
            "name": a.name,
            "description": a.description,
            "mailboxes": (
                ALL_MAILBOXES
                if ALL_MAILBOXES in a.mailboxes
                else [m.name for ref in a.mailboxes if (m := cfg.find(ref)) is not None]
            ),
            "scopes": list(a.scopes),
            "token_created_at": dates.get(a.name),
        }

    def connect_info(token: str) -> dict[str, Any]:
        return {
            "token": token,
            "mcp_url": f"{origin}/mcp",
            "header": f"Authorization: Bearer {token}",
        }

    # ── mailboxes ─────────────────────────────────────────────────────────

    @router.get("/mailboxes")
    def mailboxes(who: Principal = Depends(person)) -> dict[str, Any]:
        servers = Counter(
            (m.imap.host, m.imap.port, m.imap.tls, m.smtp.host, m.smtp.port, m.smtp.tls)
            for m in cfg.mailboxes
            if m.imap and m.smtp
        )
        suggested = None
        if servers:
            ih, ip, it, sh, sp, st = servers.most_common(1)[0][0]
            suggested = {
                "imap": {"host": ih, "port": ip, "tls": it},
                "smtp": {"host": sh, "port": sp, "tls": st},
            }
        return {"mailboxes": [mailbox_view(m) for m in cfg.mailboxes], "suggested": suggested}

    @router.post("/mailboxes")
    def add_mailbox(
        request: Request, body: dict = Body(...), who: Principal = Depends(person)
    ) -> dict[str, Any]:
        confirmed(request)
        try:
            mb = managed.save_mailbox(body, None)
        except ManageError as e:
            raise fail(e) from e
        audit.record(who.name, "manage_mailbox_added", mailbox=mb.name)
        return mailbox_view(mb)

    @router.put("/mailboxes/{name}")
    def edit_mailbox(
        name: str, request: Request, body: dict = Body(...), who: Principal = Depends(person)
    ) -> dict[str, Any]:
        confirmed(request)
        try:
            mb = managed.save_mailbox(body, name)
        except ManageError as e:
            raise fail(e) from e
        audit.record(who.name, "manage_mailbox_changed", mailbox=mb.name)
        return mailbox_view(mb)

    @router.delete("/mailboxes/{name}")
    def remove_mailbox(name: str, request: Request, who: Principal = Depends(person)) -> dict:
        confirmed(request)
        try:
            managed.delete_mailbox(name)
        except ManageError as e:
            raise fail(e) from e
        audit.record(who.name, "manage_mailbox_removed", mailbox=name)
        return {"ok": True}

    @router.post("/mailboxes/test")
    def test_mailbox(body: dict = Body(...), who: Principal = Depends(person)) -> dict[str, Any]:
        """Try the settings in the form; blank passwords use the saved ones."""
        saved = cfg.get(str(body.get("name") or ""))
        out: dict[str, Any] = {}
        for proto, model, check in (
            ("imap", ImapConfig, imap_check),
            ("smtp", SmtpConfig, smtp_check),
        ):
            part = body.get(proto)
            if not part:
                continue
            part = dict(part)
            if not part.get("password") and saved is not None and getattr(saved, proto):
                part["password"] = getattr(saved, proto).password
            try:
                conf = model.model_validate({"from_address": part.get("username", "x"), **part})
                result = check(conf)
                out[proto] = {"ok": True, "folders": result if proto == "imap" else None}
            except (ImapError, SmtpError, OSError, ValueError) as e:
                out[proto] = {"ok": False, "error": str(e) or type(e).__name__}
        return out

    # ── agents ────────────────────────────────────────────────────────────

    @router.get("/agents")
    def agents(who: Principal = Depends(person)) -> dict[str, Any]:
        dates = managed.token_dates()
        return {"agents": [agent_view(a, dates) for a in cfg.agents], "mcp_url": f"{origin}/mcp"}

    @router.post("/agents")
    def add_agent(
        request: Request, body: dict = Body(...), who: Principal = Depends(person)
    ) -> dict[str, Any]:
        confirmed(request)
        try:
            agent, token = managed.save_agent(body, None)
        except ManageError as e:
            raise fail(e) from e
        audit.record(who.name, "manage_agent_added", target=agent.name, scopes=list(agent.scopes))
        return {"agent": agent_view(agent, managed.token_dates()), **connect_info(token or "")}

    @router.put("/agents/{name}")
    def edit_agent(
        name: str, request: Request, body: dict = Body(...), who: Principal = Depends(person)
    ) -> dict[str, Any]:
        confirmed(request)
        try:
            agent, _ = managed.save_agent(body, name)
        except ManageError as e:
            raise fail(e) from e
        audit.record(
            who.name,
            "manage_agent_changed",
            target=name,
            scopes=list(agent.scopes),
            mailboxes=list(agent.mailboxes),
        )
        return {"agent": agent_view(agent, managed.token_dates())}

    @router.post("/agents/{name}/token")
    def rotate(name: str, request: Request, who: Principal = Depends(person)) -> dict[str, Any]:
        confirmed(request)
        try:
            token = managed.rotate_token(name)
        except ManageError as e:
            raise fail(e) from e
        audit.record(who.name, "manage_agent_token", target=name)
        return connect_info(token)

    @router.delete("/agents/{name}")
    def remove_agent(name: str, request: Request, who: Principal = Depends(person)) -> dict:
        confirmed(request)
        try:
            managed.delete_agent(name)
        except ManageError as e:
            raise fail(e) from e
        audit.record(who.name, "manage_agent_removed", target=name)
        return {"ok": True}

    @router.get("/export")
    def export(request: Request, who: Principal = Depends(person)) -> Response:
        confirmed(request)
        audit.record(who.name, "manage_export")
        return Response(
            managed.export_yaml(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": 'attachment; filename="mailgrant.yaml"'},
        )

    return router
