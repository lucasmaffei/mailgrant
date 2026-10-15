"""JSON API behind the web app, under /app/api.

The signed-in person is a Principal like any agent (`web.user` in the config),
so every mail call here goes through the same grants and audit as MCP and
REST. Sessions are a random token in an HttpOnly, SameSite=Strict cookie;
changing requests also need the X-Mailgrant header and a matching Origin.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .. import __version__, audit
from ..config import Config, ImapConfig, MailboxConfig
from ..grants import Forbidden, NotFound, Principal, check_sender
from ..grants import resolve as grant_resolve
from ..grants import select_imap, web_principal
from ..imap_client import ImapError
from ..imap_client import delete_message as imap_delete
from ..imap_client import fetch_attachment as imap_attachment
from ..imap_client import fetch_message as imap_fetch
from ..imap_client import mailbox_status
from ..imap_client import mark_seen as imap_mark_seen
from ..imap_client import unified_search as imap_unified_search
from ..smtp_client import SmtpError
from ..smtp_client import send as smtp_send
from .push import Pusher
from .store import Store, now

SESSION_COOKIE = "mg_session"
CSRF_HEADER = "x-mailgrant"
INVITE_TTL = timedelta(minutes=30)
# Stands in for an invite hash on a challenge started with web.setup_code.
SETUP_MARK = "setup-code"
MARK_WINDOW = timedelta(days=60)


def build_router(cfg: Config, store: Store, pusher: Pusher) -> APIRouter:
    assert cfg.web is not None
    web = cfg.web
    origin = web.origin
    rp_id = urlparse(origin).hostname or "localhost"
    secure_cookie = origin.startswith("https://")
    user_id = hashlib.sha256(web.user.name.encode()).digest()[:16]
    router = APIRouter(prefix="/app/api")

    # ── guards ────────────────────────────────────────────────────────────

    def same_origin(request: Request) -> None:
        if request.method in ("GET", "HEAD"):
            return
        if request.headers.get(CSRF_HEADER) != "1":
            raise HTTPException(403, "missing X-Mailgrant header")
        sent = request.headers.get("origin")
        if sent is not None and sent.rstrip("/") != origin:
            raise HTTPException(403, "cross-origin request refused")

    def person(request: Request) -> Principal:
        same_origin(request)
        token = request.cookies.get(SESSION_COOKIE)
        if not token or not store.session_valid(token):
            raise HTTPException(401, "not signed in")
        return web_principal(cfg)

    def open_session(response: Response, request: Request) -> None:
        token = store.create_session(web.session_days, request.headers.get("user-agent"))
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=web.session_days * 86400,
            httponly=True,
            secure=secure_cookie,
            samesite="strict",
            path="/app",
        )

    def mailbox(who: Principal, name: str, scope: str, action: str, **fields: Any) -> MailboxConfig:
        try:
            mb = grant_resolve(cfg, who, name)
            who.require(scope)
        except NotFound as e:
            raise HTTPException(404, str(e)) from e
        except Forbidden as e:
            audit.record(who.name, action, "denied", mailbox=name, reason="scope", **fields)
            raise HTTPException(403, str(e)) from e
        if mb.imap is None and scope != "send":
            raise HTTPException(409, f"mailbox {mb.name!r} has no IMAP configured")
        return mb

    def imap_of(mb: MailboxConfig) -> ImapConfig:
        if mb.imap is None:
            raise HTTPException(409, f"mailbox {mb.name!r} has no IMAP configured")
        return mb.imap

    def address(mb: MailboxConfig) -> str:
        return mb.imap.username if mb.imap else mb.smtp.username if mb.smtp else mb.name

    # ── session & passkeys ────────────────────────────────────────────────

    def setup_code_open() -> bool:
        # The setup code only bootstraps: once any passkey exists it stops
        # working, so a leaked .env can't add a device later.
        return bool(web.setup_code) and not store.credentials()

    def is_setup_code(value: str) -> bool:
        return (
            setup_code_open()
            and web.setup_code is not None
            and hmac.compare_digest(value.encode(), web.setup_code.encode())
        )

    @router.get("/auth/state")
    def auth_state(request: Request) -> dict[str, Any]:
        token = request.cookies.get(SESSION_COOKIE)
        return {
            "authenticated": bool(token and store.session_valid(token)),
            "has_passkeys": bool(store.credentials()),
            "setup_code": setup_code_open(),
            "user": web.user.name,
        }

    @router.post("/auth/register/options")
    def register_options(request: Request, body: dict = Body(...)) -> dict[str, Any]:
        same_origin(request)
        invite = str(body.get("invite") or "")
        token = request.cookies.get(SESSION_COOKIE)
        signed_in = bool(token and store.session_valid(token))
        # A signed-in person may add a device directly; anyone else needs an
        # invite, or the setup code while there is no passkey yet.
        by_setup = not signed_in and is_setup_code(invite.strip())
        if not signed_in and not by_setup and not store.invite_valid(invite):
            raise HTTPException(403, "invite missing, used or expired")
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name="mailgrant",
            user_id=user_id,
            user_name=web.user.name,
            user_display_name=web.user.name,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            exclude_credentials=[
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["id"]))
                for c in store.credentials()
            ],
        )
        invite_hash = (
            None
            if signed_in
            else SETUP_MARK if by_setup else hashlib.sha256(invite.encode()).hexdigest()
        )
        cid = store.put_challenge("register", options.challenge, invite_hash)
        return {"challenge_id": cid, "options": json.loads(options_to_json(options))}

    @router.post("/auth/register/verify")
    def register_verify(request: Request, response: Response, body: dict = Body(...)) -> dict:
        same_origin(request)
        row = store.take_challenge(str(body.get("challenge_id") or ""), "register")
        if row is None:
            raise HTTPException(400, "challenge expired, start again")
        try:
            verified = verify_registration_response(
                credential=body.get("credential") or {},
                expected_challenge=row["challenge"],
                expected_rp_id=rp_id,
                expected_origin=origin,
                require_user_verification=True,
            )
        except Exception as e:  # noqa: BLE001 - library raises several types
            raise HTTPException(400, f"passkey not accepted: {e}") from e
        if row["invite_hash"] == SETUP_MARK:
            if not setup_code_open():
                raise HTTPException(403, "setup code no longer works: a passkey already exists")
        elif row["invite_hash"] is not None and not store.use_invite(row["invite_hash"]):
            raise HTTPException(403, "invite already used or expired")
        transports = (body.get("credential") or {}).get("response", {}).get("transports") or []
        name = str(body.get("name") or "Passkey")[:60]
        store.add_credential(
            bytes_to_base64url(verified.credential_id),
            verified.credential_public_key,
            verified.sign_count,
            name,
            [str(t) for t in transports],
        )
        audit.record(
            web.user.name,
            "passkey_added",
            via_web=True,
            device=name,
            by="setup_code" if row["invite_hash"] == SETUP_MARK else None,
        )
        open_session(response, request)
        return {"ok": True}

    @router.post("/auth/login/options")
    def login_options(request: Request) -> dict[str, Any]:
        same_origin(request)
        options = generate_authentication_options(
            rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED
        )
        cid = store.put_challenge("login", options.challenge)
        return {"challenge_id": cid, "options": json.loads(options_to_json(options))}

    @router.post("/auth/login/verify")
    def login_verify(request: Request, response: Response, body: dict = Body(...)) -> dict:
        same_origin(request)
        row = store.take_challenge(str(body.get("challenge_id") or ""), "login")
        credential = body.get("credential") or {}
        cred = store.credential(str(credential.get("id") or ""))
        if row is None or cred is None:
            raise HTTPException(401, "passkey not recognized")
        try:
            verified = verify_authentication_response(
                credential=credential,
                expected_challenge=row["challenge"],
                expected_rp_id=rp_id,
                expected_origin=origin,
                credential_public_key=cred["public_key"],
                credential_current_sign_count=cred["sign_count"],
                require_user_verification=True,
            )
        except Exception as e:  # noqa: BLE001
            raise HTTPException(401, f"passkey not accepted: {e}") from e
        store.touch_credential(cred["id"], verified.new_sign_count)
        open_session(response, request)
        return {"ok": True}

    @router.post("/auth/logout")
    def logout(request: Request, response: Response) -> dict:
        same_origin(request)
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            store.end_session(token)
        response.delete_cookie(SESSION_COOKIE, path="/app")
        return {"ok": True}

    @router.get("/passkeys")
    def passkeys(who: Principal = Depends(person)) -> dict[str, Any]:
        return {
            "passkeys": [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "created_at": c["created_at"],
                    "last_used_at": c["last_used_at"],
                }
                for c in store.credentials()
            ]
        }

    @router.delete("/passkeys/{cred_id}")
    def delete_passkey(cred_id: str, who: Principal = Depends(person)) -> dict:
        if len(store.credentials()) <= 1:
            raise HTTPException(409, "this is the only passkey; add another device first")
        if not store.delete_credential(cred_id):
            raise HTTPException(404, "passkey not found")
        audit.record(who.name, "passkey_removed", via_web=True)
        return {"ok": True}

    @router.post("/invites")
    def create_invite(who: Principal = Depends(person)) -> dict[str, Any]:
        token = store.create_invite(INVITE_TTL)
        return {"url": f"{origin}/app/#/invite/{token}", "expires_in_minutes": 30}

    # ── mail ──────────────────────────────────────────────────────────────

    def marks() -> tuple[dict[tuple[str, str], str], dict[str, str]]:
        read: dict[tuple[str, str], str] = {}
        replied: dict[str, str] = {}
        for r in store.agent_marks(now() - MARK_WINDOW):
            if r["action"] == "get_message" and r["mailbox"] and r["uid"]:
                read[(r["mailbox"], str(r["uid"]))] = r["agent"]
            elif r["action"] == "send" and r["in_reply_to"]:
                replied[r["in_reply_to"]] = r["agent"]
        return read, replied

    def summary(m: dict[str, Any], read, replied) -> dict[str, Any]:
        name, addr = parseaddr(m.get("from") or "")
        try:
            ts = parsedate_to_datetime(m.get("date") or "").timestamp()
        except (TypeError, ValueError):
            ts = 0
        mark = None
        if m.get("message_id") and m["message_id"] in replied:
            mark = f"{replied[m['message_id']]} respondeu"
        elif (m.get("mailbox"), str(m.get("uid"))) in read:
            mark = f"{read[(m['mailbox'], str(m['uid']))]} leu"
        return {
            "uid": m.get("uid"),
            "mailbox": m.get("mailbox"),
            "mailbox_address": m.get("mailbox_address"),
            "from": name or addr,
            "from_address": addr,
            "subject": m.get("subject") or "",
            "date": m.get("date"),
            "ts": ts,
            "unread": "\\Seen" not in (m.get("flags") or []),
            "message_id": m.get("message_id"),
            "mark": mark,
        }

    @router.get("/me")
    def me(who: Principal = Depends(person)) -> dict[str, Any]:
        boxes = []
        for mb in who.visible(cfg):
            froms = []
            if mb.smtp is not None:
                froms = [mb.smtp.from_address] + [a for a in mb.smtp.allowed_from]
            boxes.append(
                {
                    "name": mb.name,
                    "address": address(mb),
                    "imap": mb.imap is not None,
                    "smtp": mb.smtp is not None,
                    "from_options": froms,
                }
            )
        return {
            "user": who.name,
            "scopes": sorted(who.scopes),
            "mailboxes": boxes,
            "version": __version__,
        }

    @router.get("/counts")
    def counts(who: Principal = Depends(person)) -> dict[str, Any]:
        targets = [m for m in who.visible(cfg) if m.imap is not None]

        def one(mb: MailboxConfig) -> tuple[str, int | None]:
            try:
                st = mailbox_status(mb.imap)  # type: ignore[arg-type]
                return mb.name, st["unseen"]
            except (ImapError, OSError):
                return mb.name, None

        with ThreadPoolExecutor(max_workers=max(1, len(targets))) as ex:
            unseen = dict(ex.map(one, targets))
        return {"unseen": unseen, "total": sum(v for v in unseen.values() if v)}

    @router.get("/inbox")
    def inbox(
        who: Principal = Depends(person),
        mailbox: str | None = Query(None),
        q: str | None = Query(None, max_length=200),
        unseen: bool | None = Query(None),
        limit: int = Query(40, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            who.require("read")
            targets = select_imap(cfg, who, None if mailbox in (None, "", "all") else mailbox)
        except Forbidden as e:
            raise HTTPException(403, str(e)) from e
        except NotFound as e:
            raise HTTPException(404, str(e)) from e
        result = imap_unified_search(targets, limit=limit, text=q or None, unseen=unseen)
        read, replied = marks()
        return {
            "messages": [summary(m, read, replied) for m in result["messages"]],
            "errors": result["errors"],
        }

    @router.get("/messages/{name}/{uid}")
    def message(
        name: str, uid: str, folder: str | None = None, who: Principal = Depends(person)
    ) -> dict[str, Any]:
        mb = mailbox(who, name, "read", "get_message", uid=uid)
        try:
            msg = imap_fetch(imap_of(mb), uid, folder=folder, reader=True)
        except ImapError as e:
            raise HTTPException(502, str(e)) from e
        audit.record(who.name, "get_message", mailbox=mb.name, uid=uid, folder=folder)
        sender, sender_addr = parseaddr(msg.get("from") or "")
        history = []
        for r in store.agent_marks(now() - MARK_WINDOW):
            if r["action"] == "get_message" and r["mailbox"] == mb.name and str(r["uid"]) == uid:
                history.append({"agent": r["agent"], "what": "leu", "ts": r["ts"]})
            elif (
                r["action"] == "send"
                and msg.get("message_id")
                and r["in_reply_to"] == msg["message_id"]
            ):
                history.append({"agent": r["agent"], "what": "respondeu", "ts": r["ts"]})
        return {
            "uid": uid,
            "mailbox": mb.name,
            "mailbox_address": address(mb),
            "from": sender or sender_addr,
            "from_address": sender_addr,
            "to": msg.get("to"),
            "cc": msg.get("cc"),
            "subject": msg.get("subject") or "",
            "date": msg.get("date"),
            "message_id": msg.get("message_id"),
            "references": msg.get("references"),
            "body": msg.get("body_reader") or msg.get("body_text") or "",
            "attachments": msg.get("attachments") or [],
            "agents": history,
            "can": {
                "reply": who.has("send") and mb.smtp is not None,
                "mark": who.has("mark"),
                "trash": who.has("delete"),
            },
        }

    @router.get("/messages/{name}/{uid}/attachments/{index}")
    def attachment(
        name: str,
        uid: str,
        index: int,
        folder: str | None = None,
        who: Principal = Depends(person),
    ) -> Response:
        mb = mailbox(who, name, "read", "get_attachment", uid=uid)
        try:
            filename, ctype, payload = imap_attachment(imap_of(mb), uid, index, folder=folder)
        except ImapError as e:
            raise HTTPException(404, str(e)) from e
        safe = "".join(ch for ch in filename if ch.isprintable() and ch not in '"\\') or "anexo"
        # Always a download: an attachment rendered inline could run script in our origin.
        return Response(
            payload,
            media_type="application/octet-stream" if ctype.startswith("text/") else ctype,
            headers={
                "Content-Disposition": f'attachment; filename="{safe}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.post("/messages/{name}/{uid}/seen")
    def seen(
        name: str, uid: str, body: dict = Body(default={}), who: Principal = Depends(person)
    ) -> dict:
        mb = mailbox(who, name, "mark", "mark_seen", uid=uid)
        flag = bool(body.get("seen", True))
        try:
            imap_mark_seen(imap_of(mb), uid, folder=body.get("folder"), seen=flag)
        except ImapError as e:
            raise HTTPException(502, str(e)) from e
        audit.record(who.name, "mark_seen", mailbox=mb.name, uid=uid, seen=flag)
        return {"ok": True}

    @router.post("/messages/{name}/{uid}/trash")
    def trash(
        name: str, uid: str, body: dict = Body(default={}), who: Principal = Depends(person)
    ) -> dict:
        mb = mailbox(who, name, "delete", "delete_message", uid=uid)
        try:
            result = imap_delete(imap_of(mb), uid, folder=body.get("folder"), permanent=False)
        except ImapError as e:
            raise HTTPException(502, str(e)) from e
        audit.record(
            who.name, "delete_message", mailbox=mb.name, uid=uid, moved_to=result.get("moved_to")
        )
        return result

    @router.post("/send")
    def send(body: dict = Body(...), who: Principal = Depends(person)) -> dict[str, Any]:
        mb = mailbox(who, str(body.get("mailbox") or ""), "send", "send")
        if mb.smtp is None:
            raise HTTPException(409, f"mailbox {mb.name!r} has no SMTP configured")
        to = [str(x) for x in body.get("to") or [] if str(x).strip()]
        cc = [str(x) for x in body.get("cc") or [] if str(x).strip()]
        if not to:
            raise HTTPException(422, "at least one recipient")
        try:
            check_sender(mb.smtp, body.get("from_address"))
        except Forbidden as e:
            raise HTTPException(403, str(e)) from e
        copy_to = (mb.imap, mb.smtp.save_copy_to) if mb.imap and mb.smtp.save_copy_to else None
        try:
            result = smtp_send(
                mb.smtp,
                to=to,
                cc=cc,
                subject=str(body.get("subject") or ""),
                body_text=str(body.get("body_text") or ""),
                from_address=body.get("from_address") or None,
                in_reply_to=body.get("in_reply_to") or None,
                references=body.get("references") or None,
                copy_to=copy_to,
            )
        except SmtpError as e:
            raise HTTPException(502, str(e)) from e
        audit.record(
            who.name,
            "send",
            mailbox=mb.name,
            to=to + cc,
            message_id=result.get("message_id"),
            in_reply_to=body.get("in_reply_to"),
        )
        return result

    # ── agents ────────────────────────────────────────────────────────────

    @router.get("/activity")
    def activity(
        kind: str | None = Query(None, pattern="^(all|sent|denied)$"),
        limit: int = Query(100, ge=1, le=500),
        who: Principal = Depends(person),
    ) -> dict[str, Any]:
        rows = store.agent_activity(None if kind in (None, "all") else kind, limit)
        addresses = {m.name: address(m) for m in cfg.mailboxes}
        out = []
        for r in rows:
            extra = json.loads(r["fields"] or "{}")
            out.append(
                {
                    "ts": r["ts"],
                    "agent": r["agent"],
                    "action": r["action"],
                    "outcome": r["outcome"],
                    "mailbox": addresses.get(r["mailbox"] or "", r["mailbox"]),
                    "mailbox_name": r["mailbox"],
                    "uid": r["uid"],
                    "to": extra.get("to"),
                    "reason": extra.get("reason"),
                    "moved_to": extra.get("moved_to"),
                    "mailboxes": extra.get("mailboxes"),
                }
            )
        return {"events": out}

    @router.get("/agents")
    def agents(who: Principal = Depends(person)) -> dict[str, Any]:
        out = []
        for a in cfg.agents:
            boxes = (
                "*"
                if "*" in a.mailboxes
                else [address(m) for ref in a.mailboxes if (m := cfg.find(ref)) is not None]
            )
            out.append(
                {
                    "name": a.name,
                    "description": a.description,
                    "mailboxes": boxes,
                    "scopes": list(a.scopes),
                }
            )
        return {"agents": out, "legacy_tokens": len(cfg.auth.tokens)}

    # ── notifications ─────────────────────────────────────────────────────

    def notify_prefs(who: Principal) -> dict[str, Any]:
        saved = store.get_pref("notify", {})
        names = [m.name for m in who.visible(cfg) if m.imap is not None]
        return {
            "notify": {n: bool(saved.get(n, True)) for n in names},
            "notify_agent_send": bool(store.get_pref("notify_agent_send", True)),
        }

    @router.get("/prefs")
    def get_prefs(who: Principal = Depends(person)) -> dict[str, Any]:
        return notify_prefs(who)

    @router.put("/prefs")
    def put_prefs(body: dict = Body(...), who: Principal = Depends(person)) -> dict[str, Any]:
        current = notify_prefs(who)
        if isinstance(body.get("notify"), dict):
            merged = {
                **current["notify"],
                **{k: bool(v) for k, v in body["notify"].items() if k in current["notify"]},
            }
            store.set_pref("notify", merged)
        if "notify_agent_send" in body:
            store.set_pref("notify_agent_send", bool(body["notify_agent_send"]))
        return notify_prefs(who)

    @router.get("/push/key")
    def push_key(who: Principal = Depends(person)) -> dict[str, str]:
        return {"key": pusher.public_key()}

    @router.post("/push/subscribe")
    def push_subscribe(
        request: Request, body: dict = Body(...), who: Principal = Depends(person)
    ) -> dict:
        keys = body.get("keys") or {}
        endpoint = str(body.get("endpoint") or "")
        if not endpoint.startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
            raise HTTPException(422, "invalid push subscription")
        store.add_push(
            endpoint, str(keys["p256dh"]), str(keys["auth"]), request.headers.get("user-agent")
        )
        return {"ok": True}

    @router.post("/push/unsubscribe")
    def push_unsubscribe(body: dict = Body(...), who: Principal = Depends(person)) -> dict:
        store.remove_push(str(body.get("endpoint") or ""))
        return {"ok": True}

    @router.post("/push/test")
    def push_test(who: Principal = Depends(person)) -> dict:
        sent = pusher.send_all(
            {
                "title": "mailgrant",
                "body": "As notificações estão funcionando.",
                "tag": "test",
                "url": "/app/#/settings",
            }
        )
        return {"sent": sent}

    return router


def agent_send_notifier(cfg: Config, store: Store, pusher: Pusher):
    """Audit sink: store every entry, and push when an agent sends mail."""
    assert cfg.web is not None
    person_name = cfg.web.user.name
    addresses = {
        m.name: (m.imap.username if m.imap else m.smtp.username if m.smtp else m.name)
        for m in cfg.mailboxes
    }

    def sink(entry: dict[str, Any]) -> None:
        if entry.pop("via_web", False) and entry["action"].startswith("passkey"):
            return  # account events stay in the log, not in the agents' history
        via = "person" if entry["agent"] == person_name else "agent"
        store.add_audit(entry, via)
        if (
            via == "agent"
            and entry["action"] == "send"
            and entry["outcome"] == "ok"
            and store.get_pref("notify_agent_send", True)
        ):
            payload = {
                "title": f"{entry['agent']} enviou um e-mail",
                "body": f"De {addresses.get(entry.get('mailbox') or '', '')} para "
                + ", ".join(entry.get("to") or []),
                "tag": f"agent-send:{entry.get('message_id')}",
                "url": "/app/#/agents",
            }
            threading.Thread(target=pusher.send_all, args=(payload,), daemon=True).start()

    return sink
