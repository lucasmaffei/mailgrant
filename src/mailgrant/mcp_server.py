"""MCP streamable-HTTP server exposing the same operations as the HTTP API.

Tool design: ONE flat set of tools. Each operation that targets a specific
mailbox takes a `mailbox` argument (mailbox name OR its address). This keeps
the tool catalog constant-sized regardless of how many mailboxes are
configured — agents discover available mailboxes via the `mailboxes` tool
and pass the chosen one as a parameter.

Each tool needs one scope (`read`, `mark`, `delete` or `send`). `tools/list`
only shows the tools the calling agent may use, and every call is checked
against its grant again — the list is a courtesy, the check is the rule.

This module exposes a `StreamableHTTPSessionManager` and a lifespan helper
that the FastAPI app mounts under `/mcp`. There is no stdio transport.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any, AsyncIterator, Callable

import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from . import __version__, audit
from .config import Config, MailboxConfig
from .grants import Forbidden, NotFound, Principal, check_sender
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
from .smtp_client import SmtpError
from .smtp_client import send as smtp_send

_MAILBOX_ARG: dict[str, Any] = {
    "type": "string",
    "description": (
        "Target mailbox — accepts the mailbox `name` from config or its "
        "email address (IMAP/SMTP username). Use the `mailboxes` tool to "
        "discover what's available."
    ),
}

_SEARCH_PROPS: dict[str, Any] = {
    "folder": {"type": "string"},
    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
    "from": {"type": "string", "description": "Filter by From address"},
    "to": {"type": "string"},
    "subject": {"type": "string"},
    "body": {"type": "string"},
    "text": {"type": "string", "description": "Full-text search"},
    "since": {"type": "string", "description": "IMAP date e.g. 1-Jan-2026"},
    "before": {"type": "string"},
    "unseen": {"type": "boolean"},
    "seen": {"type": "boolean"},
    "flagged": {"type": "boolean"},
    "answered": {"type": "boolean"},
    "larger_than": {"type": "integer", "minimum": 0},
    "smaller_than": {"type": "integer", "minimum": 0},
}


def _search_kwargs(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "folder": args.get("folder"),
        "limit": int(args.get("limit", 50)),
        "from_": args.get("from"),
        "to": args.get("to"),
        "subject": args.get("subject"),
        "body": args.get("body"),
        "text": args.get("text"),
        "since": args.get("since"),
        "before": args.get("before"),
        "unseen": args.get("unseen"),
        "seen": args.get("seen"),
        "flagged": args.get("flagged"),
        "answered": args.get("answered"),
        "larger_than": args.get("larger_than"),
        "smaller_than": args.get("smaller_than"),
    }


def _require_imap(mb: MailboxConfig) -> Any:
    if mb.imap is None:
        raise ValueError(f"mailbox {mb.name!r} has no IMAP configured")
    return mb.imap


def _require_smtp(mb: MailboxConfig) -> Any:
    if mb.smtp is None:
        raise ValueError(f"mailbox {mb.name!r} has no SMTP configured")
    return mb.smtp


Handler = Callable[[dict[str, Any], Principal], Any]

# The scope each tool needs. Discovery tools need `read` like the rest of the
# read path; `whoami` needs nothing so any agent can learn its own grant.
TOOL_SCOPES: dict[str, str | None] = {
    "whoami": None,
    "mailboxes": "read",
    "inbox": "read",
    "list_folders": "read",
    "list_messages": "read",
    "search": "read",
    "get_message": "read",
    "mark_seen": "mark",
    "delete_message": "delete",
    "send": "send",
}


def _mailbox(cfg: Config, who: Principal, args: dict[str, Any], tool: str) -> MailboxConfig:
    """Resolve the `mailbox` argument within the caller's grant (audits denials)."""
    ident = str(args.get("mailbox") or "")
    try:
        return grant_resolve(cfg, who, ident)
    except NotFound:
        audit.record(who.name, tool, "denied", mailbox=ident, reason="not_found")
        raise


def _build_tools(
    cfg: Config,
) -> tuple[list[types.Tool], dict[str, Handler]]:
    tools: list[types.Tool] = []
    handlers: dict[str, Handler] = {}

    tools.append(
        types.Tool(
            name="whoami",
            description=(
                "Show which agent this token belongs to, its scopes "
                "(read / mark / delete / send) and the mailboxes it may use."
            ),
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        )
    )

    def _whoami(_args: dict[str, Any], who: Principal, _c: Config = cfg) -> dict[str, Any]:
        return {
            "agent": who.name,
            "scopes": sorted(who.scopes),
            "mailboxes": [m.name for m in who.visible(_c)],
            "all_mailboxes": who.mailboxes is None,
        }

    handlers["whoami"] = _whoami

    # ── Discovery ────────────────────────────────────────────────────────
    tools.append(
        types.Tool(
            name="mailboxes",
            description=(
                "List the mailboxes this agent may use, with their capabilities. "
                "Each entry has `name`, `description`, `address` (the IMAP/SMTP "
                "username if set), and booleans `imap`/`smtp` indicating which "
                "protocols are wired up. Pass `name` or `address` as the "
                "`mailbox` argument to other tools."
            ),
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        )
    )

    def _mailboxes(_args: dict[str, Any], who: Principal, _c: Config = cfg) -> dict[str, Any]:
        return {
            "mailboxes": [
                {
                    "name": m.name,
                    "description": m.description,
                    "address": (
                        m.imap.username
                        if m.imap is not None
                        else m.smtp.username if m.smtp is not None else None
                    ),
                    "imap": m.imap is not None,
                    "smtp": m.smtp is not None,
                }
                for m in who.visible(_c)
            ]
        }

    handlers["mailboxes"] = _mailboxes

    # Mailboxes managed from the web app can appear while running, so every
    # tool is registered up front; each one still checks the mailbox it gets.
    live = cfg.managed

    # ── Unified inbox ────────────────────────────────────────────────────
    if live or any(mb.imap is not None for mb in cfg.mailboxes):
        _register_unified(cfg, tools, handlers)

    # ── IMAP ops (only if at least one mailbox has IMAP) ─────────────────
    if live or any(mb.imap is not None for mb in cfg.mailboxes):
        _register_imap_tools(cfg, tools, handlers)

    # ── SMTP ops (only if at least one mailbox has SMTP) ─────────────────
    if live or any(mb.smtp is not None for mb in cfg.mailboxes):
        _register_smtp_tools(cfg, tools, handlers)

    return tools, handlers


def _register_unified(
    cfg: Config,
    tools: list[types.Tool],
    handlers: dict[str, Handler],
) -> None:
    schema_props: dict[str, Any] = {
        "mailbox": {
            "type": "string",
            "description": (
                "CSV of mailbox names or email addresses to restrict the search "
                "to. Omit for all IMAP mailboxes."
            ),
        },
        **_SEARCH_PROPS,
    }

    tools.append(
        types.Tool(
            name="inbox",
            description=(
                "Unified inbox across every IMAP mailbox this agent may use. Returns a "
                "merged, newest-first feed. Use `mailbox` (CSV) to filter by "
                "mailbox name or email address. Use `from`, `subject`, etc. to "
                "filter content. Each result is tagged with its source `mailbox` "
                "and `mailbox_address`."
            ),
            inputSchema={
                "type": "object",
                "properties": schema_props,
                "additionalProperties": False,
            },
        )
    )

    def _inbox(args: dict[str, Any], who: Principal, _c: Config = cfg) -> dict[str, Any]:
        filter_csv = args.get("mailbox")
        targets = select_imap(_c, who, str(filter_csv) if filter_csv else None)
        audit.record(who.name, "inbox", mailboxes=[m.name for m in targets])
        return imap_unified_search(targets, **_search_kwargs(args))

    handlers["inbox"] = _inbox


def _register_imap_tools(
    cfg: Config,
    tools: list[types.Tool],
    handlers: dict[str, Handler],
) -> None:
    tools.append(
        types.Tool(
            name="list_folders",
            description="List IMAP folders in the given mailbox.",
            inputSchema={
                "type": "object",
                "properties": {"mailbox": _MAILBOX_ARG},
                "required": ["mailbox"],
                "additionalProperties": False,
            },
        )
    )

    def _list_folders(args: dict[str, Any], who: Principal, _c: Config = cfg) -> dict[str, Any]:
        mb = _mailbox(_c, who, args, "list_folders")
        return {"folders": imap_list_folders(_require_imap(mb))}

    handlers["list_folders"] = _list_folders

    tools.append(
        types.Tool(
            name="list_messages",
            description=(
                "List recent messages from a mailbox. Returns newest-first "
                "headers; `uid` is what other tools want."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mailbox": _MAILBOX_ARG,
                    "folder": {"type": "string", "description": "IMAP folder (default INBOX)"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
                    "search": {
                        "type": "string",
                        "description": "IMAP SEARCH criteria, e.g. 'UNSEEN' or 'FROM foo@bar'",
                        "default": "ALL",
                    },
                },
                "required": ["mailbox"],
                "additionalProperties": False,
            },
        )
    )

    def _list_messages(args: dict[str, Any], who: Principal, _c: Config = cfg) -> dict[str, Any]:
        mb = _mailbox(_c, who, args, "list_messages")
        return {
            "messages": imap_list_messages(
                _require_imap(mb),
                folder=args.get("folder"),
                limit=int(args.get("limit", 50)),
                search=str(args.get("search", "ALL")),
            )
        }

    handlers["list_messages"] = _list_messages

    tools.append(
        types.Tool(
            name="search",
            description=(
                "Structured search in a single mailbox. Filter by from/to/"
                "subject/body/text/dates/flags/size. Returns newest-first headers."
            ),
            inputSchema={
                "type": "object",
                "properties": {"mailbox": _MAILBOX_ARG, **_SEARCH_PROPS},
                "required": ["mailbox"],
                "additionalProperties": False,
            },
        )
    )

    def _search(args: dict[str, Any], who: Principal, _c: Config = cfg) -> dict[str, Any]:
        mb = _mailbox(_c, who, args, "search")
        return {"messages": imap_search_messages(_require_imap(mb), **_search_kwargs(args))}

    handlers["search"] = _search

    tools.append(
        types.Tool(
            name="get_message",
            description=(
                "Fetch a full message (incl. body) from a mailbox by UID. "
                "Pass `reader=true` to also include `body_reader` — a clean, "
                "readable text/markdown version of the HTML body with chrome "
                "stripped (no tables, styles, tracking pixels, just the words). "
                "Best for LLMs that don't want to read raw HTML."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mailbox": _MAILBOX_ARG,
                    "uid": {"type": "string"},
                    "folder": {"type": "string"},
                    "reader": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include `body_reader` (HTML stripped to readable text).",
                    },
                },
                "required": ["mailbox", "uid"],
                "additionalProperties": False,
            },
        )
    )

    def _get_message(args: dict[str, Any], who: Principal, _c: Config = cfg) -> dict[str, Any]:
        mb = _mailbox(_c, who, args, "get_message")
        audit.record(
            who.name, "get_message", mailbox=mb.name, uid=args.get("uid"), folder=args.get("folder")
        )
        return imap_fetch(
            _require_imap(mb),
            str(args["uid"]),
            folder=args.get("folder"),
            reader=bool(args.get("reader", False)),
        )

    handlers["get_message"] = _get_message

    tools.append(
        types.Tool(
            name="delete_message",
            description=(
                "Move a message to the mailbox's trash folder. Pass `permanent=true` "
                "to erase it instead (required when it is already in the trash)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mailbox": _MAILBOX_ARG,
                    "uid": {"type": "string"},
                    "folder": {"type": "string"},
                    "permanent": {"type": "boolean", "default": False},
                },
                "required": ["mailbox", "uid"],
                "additionalProperties": False,
            },
        )
    )

    def _del(args: dict[str, Any], who: Principal, _c: Config = cfg) -> dict[str, Any]:
        mb = _mailbox(_c, who, args, "delete_message")
        result = imap_delete(
            _require_imap(mb),
            str(args["uid"]),
            folder=args.get("folder"),
            permanent=bool(args.get("permanent", False)),
        )
        audit.record(
            who.name,
            "delete_message",
            mailbox=mb.name,
            uid=args.get("uid"),
            moved_to=result.get("moved_to"),
            erased=result.get("erased"),
        )
        return result

    handlers["delete_message"] = _del

    tools.append(
        types.Tool(
            name="mark_seen",
            description="Set or clear the \\Seen flag on a message in a mailbox.",
            inputSchema={
                "type": "object",
                "properties": {
                    "mailbox": _MAILBOX_ARG,
                    "uid": {"type": "string"},
                    "folder": {"type": "string"},
                    "seen": {"type": "boolean", "default": True},
                },
                "required": ["mailbox", "uid"],
                "additionalProperties": False,
            },
        )
    )

    def _seen(args: dict[str, Any], who: Principal, _c: Config = cfg) -> dict[str, Any]:
        mb = _mailbox(_c, who, args, "mark_seen")
        audit.record(who.name, "mark_seen", mailbox=mb.name, uid=args.get("uid"))
        imap_mark_seen(
            _require_imap(mb),
            str(args["uid"]),
            folder=args.get("folder"),
            seen=bool(args.get("seen", True)),
        )
        return {"ok": True}

    handlers["mark_seen"] = _seen


def _register_smtp_tools(
    cfg: Config,
    tools: list[types.Tool],
    handlers: dict[str, Handler],
) -> None:
    tools.append(
        types.Tool(
            name="send",
            description=(
                "Send an email from a mailbox via SMTP. To answer a message, pass its "
                "`message_id` as `in_reply_to` so the reply lands in the same thread."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mailbox": _MAILBOX_ARG,
                    "to": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "subject": {"type": "string"},
                    "body_text": {"type": "string"},
                    "body_html": {"type": "string"},
                    "cc": {"type": "array", "items": {"type": "string"}},
                    "bcc": {"type": "array", "items": {"type": "string"}},
                    "from_address": {
                        "type": "string",
                        "description": "Only the mailbox's own address or its smtp.allowed_from",
                    },
                    "reply_to": {"type": "string"},
                    "in_reply_to": {
                        "type": "string",
                        "description": "Message-ID being answered, e.g. <abc@example.com>",
                    },
                    "references": {"type": "string"},
                },
                "required": ["mailbox", "to", "subject"],
                "additionalProperties": False,
            },
        )
    )

    def _send(args: dict[str, Any], who: Principal, _c: Config = cfg) -> dict[str, Any]:
        mb = _mailbox(_c, who, args, "send")
        smtp = _require_smtp(mb)
        rcpts = [*list(args["to"]), *list(args.get("cc") or []), *list(args.get("bcc") or [])]
        try:
            check_sender(smtp, args.get("from_address"))
        except Forbidden:
            audit.record(who.name, "send", "denied", mailbox=mb.name, reason="from_address")
            raise
        copy_to = (
            (mb.imap, smtp.save_copy_to) if mb.imap is not None and smtp.save_copy_to else None
        )
        try:
            result = smtp_send(
                smtp,
                to=list(args["to"]),
                subject=str(args["subject"]),
                body_text=args.get("body_text"),
                body_html=args.get("body_html"),
                cc=list(args.get("cc") or []),
                bcc=list(args.get("bcc") or []),
                from_address=args.get("from_address"),
                reply_to=args.get("reply_to"),
                in_reply_to=args.get("in_reply_to"),
                references=args.get("references"),
                copy_to=copy_to,
            )
        except SmtpError as e:
            audit.record(who.name, "send", "error", mailbox=mb.name, to=rcpts, error=str(e))
            raise
        audit.record(
            who.name,
            "send",
            mailbox=mb.name,
            to=rcpts,
            message_id=result.get("message_id"),
            in_reply_to=args.get("in_reply_to"),
        )
        return result

    handlers["send"] = _send


def build_mcp_app(cfg: Config) -> Server:
    """Build the low-level MCP `Server` with all tools registered for `cfg`."""
    tools, handlers = _build_tools(cfg)

    server: Server = Server("mailgrant", version=__version__)

    def _caller() -> Principal:
        # The bearer middleware stored the principal on the HTTP request, and
        # the streamable-HTTP transport hands that request to the server.
        request = server.request_context.request
        principal = getattr(getattr(request, "state", None), "principal", None)
        if not isinstance(principal, Principal):
            raise PermissionError("unauthenticated MCP request")
        return principal

    def _allowed(who: Principal, tool: str) -> bool:
        scope = TOOL_SCOPES.get(tool)
        return scope is None or who.has(scope)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        who = _caller()
        return [t for t in tools if _allowed(who, t.name)]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        who = _caller()
        fn = handlers.get(name)
        if fn is None:
            raise ValueError(f"unknown tool: {name}")
        try:
            if not _allowed(who, name):
                audit.record(
                    who.name,
                    name,
                    "denied",
                    reason="scope",
                    mailbox=(arguments or {}).get("mailbox"),
                )
                raise Forbidden(f"agent {who.name!r} lacks the {TOOL_SCOPES[name]!r} scope")
            result = fn(arguments or {}, who)
        except (ImapError, SmtpError, ValueError, NotFound, Forbidden) as e:
            return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]
        return [types.TextContent(type="text", text=json.dumps(result, default=str))]

    return server


def build_session_manager(cfg: Config) -> StreamableHTTPSessionManager:
    """Build a streamable-HTTP session manager for the MCP server.

    The returned manager must be driven by its `run()` async-context manager,
    typically from the host ASGI app's lifespan.
    """
    mcp_app = build_mcp_app(cfg)
    # stateless=True keeps things simple: no server-side session table, every
    # request carries its own correlation. Plays well behind any LB.
    return StreamableHTTPSessionManager(
        mcp_app,
        json_response=False,
        stateless=True,
    )


@contextlib.asynccontextmanager
async def mcp_lifespan(manager: StreamableHTTPSessionManager) -> AsyncIterator[None]:
    """Lifespan hook that starts/stops the MCP session manager."""
    async with manager.run():
        yield


def get_notification_options() -> NotificationOptions:
    """Exposed for callers/tests that need the default notification options."""
    return NotificationOptions()
