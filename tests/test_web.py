"""Web app: off by default, passkey sessions, the same grants as agents, push, watcher."""

from __future__ import annotations

import email
import json
from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from mailgrant import audit
from mailgrant.cli import main as cli_main
from mailgrant.config import load_config
from mailgrant.server import create_app
from mailgrant.web import html_view
from mailgrant.web.push import Pusher
from mailgrant.web.store import Store
from mailgrant.web.watcher import Watcher

AGENT = "EXAMPLE-agent-token"
ORIGIN = "https://mail.example.org"
H = {"X-Mailgrant": "1", "Origin": ORIGIN}


def config_text(tmp_path: Path, web: str | None = None) -> str:
    body = f"""
agents:
  - {{name: hermes, token: "{AGENT}", mailboxes: [alpha], scopes: [read, send]}}
mailboxes:
  - name: alpha
    imap: {{host: mail.invalid, username: alpha@example.org, password: a}}
    smtp: {{host: mail.invalid, username: alpha@example.org, password: a,
      from_address: alpha@example.org}}
  - name: beta
    imap: {{host: mail.invalid, username: beta@example.org, password: b}}
"""
    if web is not None:
        body += web.replace("DATA", str(tmp_path / "data"))
    p = tmp_path / "config.yaml"
    p.write_text(body)
    return str(p)


WEB = f"""
web:
  origin: {ORIGIN}
  data_dir: DATA
  poll_seconds: 3600
  user: {{name: lucas, mailboxes: ["*"], scopes: [read, mark, send]}}
"""


@pytest.fixture
def web_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("mailgrant.web.watcher.Watcher.start", lambda self: False)
    cfg = load_config(config_text(tmp_path, WEB))
    with TestClient(create_app(cfg), base_url=ORIGIN) as client:
        client.store = client.app.state.web_store  # type: ignore[attr-defined]
        yield client
    audit.clear_sinks()


def sign_in(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    store: Store = client.store  # type: ignore[attr-defined]
    from datetime import timedelta

    invite = store.create_invite(timedelta(minutes=5))
    monkeypatch.setattr(
        "mailgrant.web.api.verify_registration_response",
        Mock(
            return_value=SimpleNamespace(
                credential_id=b"cred-1", credential_public_key=b"pk", sign_count=0
            )
        ),
    )
    opts = client.post("/app/api/auth/register/options", headers=H, json={"invite": invite})
    assert opts.status_code == 200, opts.text
    done = client.post(
        "/app/api/auth/register/verify",
        headers=H,
        json={"challenge_id": opts.json()["challenge_id"], "name": "iPhone", "credential": {}},
    )
    assert done.status_code == 200, done.text
    return invite


# ── off by default ──────────────────────────────────────────────────────────


def test_without_web_section_nothing_changes(tmp_path: Path) -> None:
    cfg = load_config(config_text(tmp_path))
    with TestClient(create_app(cfg)) as client:
        assert client.get("/app/").status_code == 401  # just another bearer-protected path
        assert client.get("/").status_code == 401
        assert (
            client.get("/whoami", headers={"Authorization": f"Bearer {AGENT}"}).status_code == 200
        )
    assert not (tmp_path / "data").exists()


def test_enabled_false_is_off(tmp_path: Path) -> None:
    cfg = load_config(config_text(tmp_path, WEB + "  enabled: false\n"))
    assert cfg.web is not None and not cfg.web_enabled
    with TestClient(create_app(cfg)) as client:
        assert client.get("/app/").status_code == 401


def test_origin_must_be_secure(tmp_path: Path) -> None:
    from mailgrant.config import ConfigError

    with pytest.raises(ConfigError, match="secure origin"):
        load_config(config_text(tmp_path, WEB.replace(ORIGIN, "http://mail.example.org")))


# ── shell and headers ───────────────────────────────────────────────────────


def test_shell_is_served_with_strict_headers(web_client: TestClient) -> None:
    r = web_client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/app/"
    page = web_client.get("/app/")
    assert page.status_code == 200 and "app.js" in page.text
    csp = page.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert web_client.get("/app/sw.js").headers["content-type"].startswith("text/javascript")
    assert web_client.get("/app/manifest.webmanifest").status_code == 200
    assert web_client.get("/app/static/icons/icon-192.png").status_code == 200


def test_agents_still_need_their_token(web_client: TestClient) -> None:
    assert web_client.get("/mailboxes").status_code == 401
    assert (
        web_client.get("/whoami", headers={"Authorization": f"Bearer {AGENT}"}).json()["agent"]
        == "hermes"
    )


# ── sessions ────────────────────────────────────────────────────────────────


def test_api_needs_a_session(web_client: TestClient) -> None:
    assert web_client.get("/app/api/me").status_code == 401
    state = web_client.get("/app/api/auth/state").json()
    assert state == {
        "authenticated": False,
        "has_passkeys": False,
        "setup_code": False,
        "user": "lucas",
    }


def test_register_needs_a_valid_invite(web_client: TestClient) -> None:
    r = web_client.post("/app/api/auth/register/options", headers=H, json={"invite": "nope"})
    assert r.status_code == 403


def test_csrf_header_and_origin_are_enforced(web_client: TestClient) -> None:
    assert web_client.post("/app/api/auth/login/options").status_code == 403
    bad = {"X-Mailgrant": "1", "Origin": "https://evil.example"}
    assert web_client.post("/app/api/auth/login/options", headers=bad).status_code == 403
    assert web_client.post("/app/api/auth/login/options", headers=H).status_code == 200


def test_invite_registers_once_and_opens_a_session(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    invite = sign_in(web_client, monkeypatch)
    cookie = web_client.cookies.get("mg_session")
    assert cookie
    me = web_client.get("/app/api/me").json()
    assert me["user"] == "lucas" and me["scopes"] == ["mark", "read", "send"]
    assert [m["name"] for m in me["mailboxes"]] == ["alpha", "beta"]
    assert web_client.get("/app/api/passkeys").json()["passkeys"][0]["name"] == "iPhone"
    # The same invite cannot register a second device.
    web_client.cookies.clear()
    again = web_client.post("/app/api/auth/register/options", headers=H, json={"invite": invite})
    assert again.status_code == 403


SETUP = "correct-horse-battery"


def _fake_registration(monkeypatch: pytest.MonkeyPatch, cred: bytes) -> None:
    monkeypatch.setattr(
        "mailgrant.web.api.verify_registration_response",
        Mock(
            return_value=SimpleNamespace(
                credential_id=cred, credential_public_key=b"pk", sign_count=0
            )
        ),
    )


def _register(client: TestClient, code: str) -> int:
    opts = client.post("/app/api/auth/register/options", headers=H, json={"invite": code})
    if opts.status_code != 200:
        return opts.status_code
    done = client.post(
        "/app/api/auth/register/verify",
        headers=H,
        json={"challenge_id": opts.json()["challenge_id"], "name": "Mac", "credential": {}},
    )
    return done.status_code


def test_setup_code_from_env_creates_only_the_first_passkey(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mailgrant.web.watcher.Watcher.start", lambda self: False)
    monkeypatch.setenv("MAILGRANT_SETUP_CODE", f"  {SETUP} ")
    cfg = load_config(config_text(tmp_path, WEB))
    assert cfg.web is not None and cfg.web.setup_code == SETUP
    with TestClient(create_app(cfg), base_url=ORIGIN) as client:
        assert client.get("/app/api/auth/state").json()["setup_code"] is True
        _fake_registration(monkeypatch, b"cred-1")
        assert _register(client, "wrong-code-123") == 403
        assert _register(client, SETUP) == 200
        assert client.get("/app/api/me").status_code == 200
        # Once a passkey exists the code is dead, even for a fresh browser.
        client.cookies.clear()
        assert client.get("/app/api/auth/state").json()["setup_code"] is False
        _fake_registration(monkeypatch, b"cred-2")
        assert _register(client, SETUP) == 403
    audit.clear_sinks()


def test_setup_code_race_is_refused_at_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mailgrant.web.watcher.Watcher.start", lambda self: False)
    cfg = load_config(config_text(tmp_path, WEB + f"  setup_code: {SETUP}\n"))
    with TestClient(create_app(cfg), base_url=ORIGIN) as client:
        _fake_registration(monkeypatch, b"cred-1")
        a = client.post("/app/api/auth/register/options", headers=H, json={"invite": SETUP})
        b = client.post("/app/api/auth/register/options", headers=H, json={"invite": SETUP})
        assert a.status_code == b.status_code == 200
        body = {"name": "x", "credential": {}}
        first = client.post(
            "/app/api/auth/register/verify",
            headers=H,
            json={**body, "challenge_id": a.json()["challenge_id"]},
        )
        assert first.status_code == 200
        client.cookies.clear()
        _fake_registration(monkeypatch, b"cred-2")
        second = client.post(
            "/app/api/auth/register/verify",
            headers=H,
            json={**body, "challenge_id": b.json()["challenge_id"]},
        )
        assert second.status_code == 403
    audit.clear_sinks()


def test_setup_code_must_be_long(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="at least 12"):
        load_config(config_text(tmp_path, WEB + "  setup_code: short\n"))


def test_invites_survive_being_linkified(web_client: TestClient) -> None:
    from datetime import timedelta

    token = web_client.store.create_invite(timedelta(minutes=5))  # type: ignore[attr-defined]
    assert token.isalnum()


def test_login_with_a_known_passkey(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(web_client, monkeypatch)
    web_client.post("/app/api/auth/logout", headers=H)
    web_client.cookies.clear()
    assert web_client.get("/app/api/me").status_code == 401
    monkeypatch.setattr(
        "mailgrant.web.api.verify_authentication_response",
        Mock(return_value=SimpleNamespace(new_sign_count=1)),
    )
    opts = web_client.post("/app/api/auth/login/options", headers=H).json()
    from webauthn.helpers import bytes_to_base64url

    unknown = web_client.post(
        "/app/api/auth/login/verify",
        headers=H,
        json={"challenge_id": opts["challenge_id"], "credential": {"id": "x"}},
    )
    assert unknown.status_code == 401
    opts = web_client.post("/app/api/auth/login/options", headers=H).json()
    ok = web_client.post(
        "/app/api/auth/login/verify",
        headers=H,
        json={
            "challenge_id": opts["challenge_id"],
            "credential": {"id": bytes_to_base64url(b"cred-1")},
        },
    )
    assert ok.status_code == 200
    assert web_client.get("/app/api/me").status_code == 200


def test_last_passkey_cannot_be_removed(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(web_client, monkeypatch)
    pid = web_client.get("/app/api/passkeys").json()["passkeys"][0]["id"]
    assert web_client.delete(f"/app/api/passkeys/{pid}", headers=H).status_code == 409


# ── mail through the person's grant ─────────────────────────────────────────


def test_inbox_shows_agent_marks(web_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    sign_in(web_client, monkeypatch)
    search = Mock(
        return_value={
            "messages": [
                {
                    "uid": "7",
                    "mailbox": "alpha",
                    "mailbox_address": "alpha@example.org",
                    "from": "Ana <ana@x.org>",
                    "subject": "Oi",
                    "date": "Tue, 14 Oct 2026 10:00:00 -0300",
                    "flags": [],
                    "message_id": "<m7@x>",
                },
                {
                    "uid": "8",
                    "mailbox": "alpha",
                    "mailbox_address": "alpha@example.org",
                    "from": "b@x.org",
                    "subject": "Re",
                    "date": "Tue, 14 Oct 2026 09:00:00 -0300",
                    "flags": ["\\Seen"],
                    "message_id": "<m8@x>",
                },
            ],
            "errors": [],
        }
    )
    monkeypatch.setattr("mailgrant.web.api.imap_unified_search", search)
    audit.record("hermes", "get_message", mailbox="alpha", uid="7")
    audit.record("hermes", "send", mailbox="alpha", to=["b@x.org"], in_reply_to="<m8@x>")
    audit.record("lucas", "get_message", mailbox="alpha", uid="8")  # the person: no mark
    msgs = web_client.get("/app/api/inbox").json()["messages"]
    assert [(m["uid"], m["unread"], m["mark"], m["from"]) for m in msgs] == [
        ("7", True, {"agent": "hermes", "what": "read"}, "Ana"),
        ("8", False, {"agent": "hermes", "what": "replied"}, "b@x.org"),
    ]
    activity = web_client.get("/app/api/activity").json()["events"]
    assert {e["agent"] for e in activity} == {"hermes"}


def test_person_scopes_are_enforced(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(web_client, monkeypatch)
    delete = Mock()
    monkeypatch.setattr("mailgrant.web.api.imap_delete", delete)
    r = web_client.post("/app/api/messages/alpha/7/trash", headers=H, json={})
    assert r.status_code == 403  # web.user has no delete scope
    delete.assert_not_called()


def test_send_threads_and_checks_sender(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(web_client, monkeypatch)
    send = Mock(return_value={"message_id": "<new@x>"})
    monkeypatch.setattr("mailgrant.web.api.smtp_send", send)
    spoof = web_client.post(
        "/app/api/send",
        headers=H,
        json={
            "mailbox": "alpha",
            "to": ["a@x.org"],
            "subject": "s",
            "body_text": "b",
            "from_address": "ceo@x.org",
        },
    )
    assert spoof.status_code == 403
    ok = web_client.post(
        "/app/api/send",
        headers=H,
        json={
            "mailbox": "alpha",
            "to": ["a@x.org"],
            "subject": "Re: s",
            "body_text": "b",
            "in_reply_to": "<m7@x>",
            "references": "<m7@x>",
        },
    )
    assert ok.status_code == 200
    assert send.call_args.kwargs["in_reply_to"] == "<m7@x>"
    no_smtp = web_client.post(
        "/app/api/send", headers=H, json={"mailbox": "beta", "to": ["a@x.org"]}
    )
    assert no_smtp.status_code == 409


def test_message_and_attachment_download(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(web_client, monkeypatch)
    monkeypatch.setattr(
        "mailgrant.web.api.imap_fetch",
        Mock(
            return_value={
                "from": "Ana <ana@x.org>",
                "subject": "Oi",
                "date": "Tue, 14 Oct 2026 10:00:00 -0300",
                "message_id": "<m7@x>",
                "body_reader": "Texto",
                "attachments": [{"index": 0, "filename": "a.html"}],
            }
        ),
    )
    m = web_client.get("/app/api/messages/alpha/7").json()
    assert m["body"] == "Texto" and m["can"] == {"reply": True, "mark": True, "trash": False}
    monkeypatch.setattr(
        "mailgrant.web.api.imap_attachment", Mock(return_value=("a.html", "text/html", b"<script>"))
    )
    r = web_client.get("/app/api/messages/alpha/7/attachments/0")
    # Never rendered inline: an HTML attachment would run in our origin.
    assert r.headers["content-disposition"].startswith("attachment;")
    assert r.headers["content-type"] == "application/octet-stream"


# ── notifications ───────────────────────────────────────────────────────────


def test_prefs_and_push_subscription(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(web_client, monkeypatch)
    prefs = web_client.get("/app/api/prefs").json()
    assert prefs == {
        "notify": {"alpha": True, "beta": True},
        "notify_agent_send": True,
        "threads": True,
        "images": False,
        "image_senders": [],
        "lang": "",
        "ui_lang": "",
        "signatures": {"alpha": ""},
    }
    prefs = web_client.put(
        "/app/api/prefs", headers=H, json={"notify": {"beta": False, "ghost": True}}
    ).json()
    assert prefs["notify"] == {"alpha": True, "beta": False}
    prefs = web_client.put("/app/api/prefs", headers=H, json={"lang": "fr", "ui_lang": "fr"}).json()
    assert (prefs["lang"], prefs["ui_lang"]) == ("fr", "fr")
    bad_lang = web_client.put("/app/api/prefs", headers=H, json={"lang": "klingon"})
    assert bad_lang.status_code == 422
    assert (
        len(web_client.get("/app/api/push/key").json()["key"]) == 87
    )  # 65-byte P-256 point, base64url
    bad = web_client.post(
        "/app/api/push/subscribe", headers=H, json={"endpoint": "http://x", "keys": {}}
    )
    assert bad.status_code == 422
    good = web_client.post(
        "/app/api/push/subscribe",
        headers=H,
        json={"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}},
    )
    assert good.status_code == 200
    assert len(web_client.store.push_subscriptions()) == 1  # type: ignore[attr-defined]


def test_watcher_pushes_only_what_arrived(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = load_config(config_text(tmp_path, WEB))
    store = Store(str(tmp_path / "data"))
    pusher = Mock(spec=Pusher)
    w = Watcher(cfg, store, pusher)
    status = {
        "alpha": {"uidnext": 10, "uidvalidity": 1, "unseen": 0},
        "beta": {"uidnext": 5, "uidvalidity": 1, "unseen": 0},
    }
    monkeypatch.setattr(
        "mailgrant.web.watcher.mailbox_status",
        lambda imap: status["alpha" if imap.username.startswith("alpha") else "beta"],
    )
    headers = Mock(
        return_value=[{"uid": "10", "from": "Ana <ana@x.org>", "subject": "Oi", "flags": []}]
    )
    monkeypatch.setattr("mailgrant.web.watcher.headers_since", headers)

    assert w.check_once() == []  # first round: baseline only
    status["alpha"] = {"uidnext": 11, "uidvalidity": 1, "unseen": 1}
    sent = w.check_once()
    assert [p["title"] for p in sent] == ["Ana"] and sent[0]["url"] == "/app/#/m/alpha/10"
    assert sent[0]["badge"] == 1
    headers.assert_called_once()
    assert headers.call_args.args[1] == 10

    store.set_pref("notify", {"alpha": False})
    status["alpha"] = {"uidnext": 12, "uidvalidity": 1, "unseen": 2}
    assert w.check_once() == []


def test_agent_send_triggers_a_push(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "mailgrant.web.push.Pusher.send_all", lambda self, payload: calls.append(payload) or 1
    )
    monkeypatch.setattr("threading.Thread.start", lambda self: self.run())
    audit.record("hermes", "send", mailbox="alpha", to=["c@x.org"], message_id="<z@x>")
    # No language chosen yet: pushes go out in English.
    assert calls and calls[0]["title"] == "hermes sent an email"
    assert "alpha@example.org" in calls[0]["body"]


# ── CLI ─────────────────────────────────────────────────────────────────────


def test_cli_invite(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = config_text(tmp_path, WEB)
    assert cli_main(["invite", "--config", path, "--minutes", "5"]) == 0
    url = capsys.readouterr().out.strip().splitlines()[-1].strip()
    assert url.startswith(f"{ORIGIN}/app/#/invite/")
    assert Store(str(tmp_path / "data")).invite_valid(url.rsplit("/", 1)[1])
    off = config_text(tmp_path)
    assert cli_main(["invite", "--config", off]) == 1


def test_history_table_holds_no_bodies(tmp_path: Path) -> None:
    store = Store(str(tmp_path / "data"))
    store.add_audit(
        {
            "ts": "2026-10-14T00:00:00+00:00",
            "agent": "hermes",
            "action": "send",
            "outcome": "ok",
            "mailbox": "alpha",
            "to": ["x@y"],
        },
        "agent",
    )
    row = store.agent_activity(None, 10)[0]
    assert json.loads(row["fields"]) == {"to": ["x@y"]}


def test_store_survives_concurrent_first_start(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    data = str(tmp_path / "data")
    with ThreadPoolExecutor(8) as ex:
        stores = list(ex.map(lambda _: Store(data), range(8)))
    stores[0].set_pref("x", 1)
    assert stores[-1].get_pref("x") == 1


# ── organizing, conversations, drafts ───────────────────────────────────────


def _msg(uid: str, mid: str, refs: str = "", flags: list[str] | None = None) -> dict[str, Any]:
    return {
        "uid": uid,
        "mailbox": "alpha",
        "mailbox_address": "alpha@example.org",
        "from": "Ana <ana@x.org>",
        "subject": "Oi",
        "date": f"Tue, 14 Oct 2026 {10 + int(uid) % 10:02d}:00:00 -0300",
        "flags": flags or [],
        "message_id": mid,
        "in_reply_to": refs.split()[-1] if refs else "",
        "references": refs,
    }


def test_inbox_groups_conversations(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(web_client, monkeypatch)
    msgs = [
        _msg("9", "<m9@x>", "<m7@x>", ["\\Seen", "\\Flagged"]),
        _msg("8", "<m8@x>"),
        _msg("7", "<m7@x>"),
    ]
    monkeypatch.setattr(
        "mailgrant.web.api.imap_unified_search",
        Mock(return_value={"messages": msgs, "errors": []}),
    )
    rows = web_client.get("/app/api/inbox").json()["messages"]
    assert [(r["uid"], r["count"], r["members"], r["unread"], r["flagged"]) for r in rows] == [
        ("9", 2, ["9", "7"], True, True),
        ("8", 1, ["8"], True, False),
    ]
    web_client.put("/app/api/prefs", headers=H, json={"threads": False})
    rows = web_client.get("/app/api/inbox").json()["messages"]
    assert [r["uid"] for r in rows] == ["9", "8", "7"]


def test_batch_actions_follow_scopes(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(web_client, monkeypatch)
    move = Mock(return_value={"ok": True, "moved_to": "Archive", "count": 2})
    flags = Mock()
    monkeypatch.setattr("mailgrant.web.api.move_to", move)
    monkeypatch.setattr("mailgrant.web.api.set_flags", flags)
    items = [{"mailbox": "alpha", "uid": "7"}, {"mailbox": "alpha", "uid": "9"}]
    r = web_client.post("/app/api/batch", headers=H, json={"action": "archive", "items": items})
    assert r.status_code == 200 and r.json()["moved_to"] == {"alpha": "Archive"}
    assert move.call_args.args[1:] == (["7", "9"], "archive")
    # web.user has no delete scope: the trash is refused before any IMAP call.
    move.reset_mock()
    r = web_client.post("/app/api/batch", headers=H, json={"action": "trash", "items": items})
    assert r.status_code == 403
    move.assert_not_called()
    r = web_client.post(
        "/app/api/batch",
        headers=H,
        json={"action": "flag", "items": [{"mailbox": "beta", "uid": "3"}]},
    )
    assert r.status_code == 200
    assert flags.call_args.args[1:] == (["3"], "flagged", True)
    assert (
        web_client.post(
            "/app/api/batch", headers=H, json={"action": "explode", "items": items}
        ).status_code
        == 422
    )


def test_drafts_replace_the_old_version_and_go_when_sent(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import base64
    import email

    sign_in(web_client, monkeypatch)
    stored: list[bytes] = []
    monkeypatch.setattr("mailgrant.web.api.special_folder", lambda cfg, kind: "Drafts")
    monkeypatch.setattr(
        "mailgrant.web.api.append_message",
        lambda cfg, folder, raw, flags: stored.append(raw) or "55",
    )
    fetched = Mock(return_value=[("old.pdf", "application/pdf", b"%PDF")])
    monkeypatch.setattr("mailgrant.web.api.fetch_attachments", fetched)
    drop = Mock()
    monkeypatch.setattr("mailgrant.web.api.delete_draft", drop)
    body = {
        "mailbox": "alpha",
        "to": ["Ana <ana@x.org>"],
        "bcc": ["hidden@x.org"],
        "subject": "Proposta",
        "body_text": "Segue.",
        "attachments": [
            {
                "filename": "nota.txt",
                "content_type": "text/plain",
                "data": base64.b64encode(b"oi").decode(),
            },
            {"ref": {"mailbox": "alpha", "folder": "Drafts", "uid": "50", "index": 0}},
        ],
        "replace": {"mailbox": "alpha", "uid": "50"},
    }
    r = web_client.put("/app/api/drafts", headers=H, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["uid"] == "55"
    assert [a["filename"] for a in r.json()["attachments"]] == ["nota.txt", "old.pdf"]
    assert fetched.call_args.args[1:] == ("50", [0])
    assert drop.call_args.args[1:] == ("50", "Drafts")
    saved = email.message_from_bytes(stored[0])
    assert saved["Bcc"] == "hidden@x.org"
    assert [p.get_filename() for p in saved.walk() if p.get_filename()] == ["nota.txt", "old.pdf"]

    send = Mock(return_value={"message_id": "<new@x>"})
    monkeypatch.setattr("mailgrant.web.api.smtp_send", send)
    drop.reset_mock()
    r = web_client.post(
        "/app/api/send",
        headers=H,
        json={**body, "replace": None, "draft": {"mailbox": "alpha", "uid": "55"}},
    )
    assert r.status_code == 200, r.text
    assert send.call_args.kwargs["bcc"] == ["hidden@x.org"]
    assert len(send.call_args.kwargs["attachments"]) == 2
    assert drop.call_args.args[1:] == ("55", "Drafts")


def test_attachments_are_checked(web_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import base64

    sign_in(web_client, monkeypatch)
    send = Mock(return_value={})
    monkeypatch.setattr("mailgrant.web.api.smtp_send", send)
    base = {"mailbox": "alpha", "to": ["a@x.org"], "subject": "s", "body_text": "b"}
    ghost = [{"ref": {"mailbox": "ghost", "uid": "1", "index": 0}}]
    r = web_client.post("/app/api/send", headers=H, json={**base, "attachments": ghost})
    assert r.status_code == 404
    junk = [{"filename": "a", "data": "%%%"}]
    r = web_client.post("/app/api/send", headers=H, json={**base, "attachments": junk})
    assert r.status_code == 422
    monkeypatch.setattr("mailgrant.web.api.MAX_ATTACHMENT_BYTES", 10)
    big = [{"filename": "a", "data": base64.b64encode(b"x" * 11).decode()}]
    r = web_client.post("/app/api/send", headers=H, json={**base, "attachments": big})
    assert r.status_code == 413
    send.assert_not_called()


def test_sent_view_says_who_sent_it(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(web_client, monkeypatch)
    monkeypatch.setattr("mailgrant.web.api.special_folder", lambda cfg, kind: "Sent")
    sent = [
        {
            "uid": "3",
            "to": "Ana <ana@x.org>, b@x.org",
            "subject": "Re: Oi",
            "flags": ["\\Seen"],
            "date": "Tue, 14 Oct 2026 11:00:00 -0300",
            "message_id": "<s3@x>",
        },
        {
            "uid": "2",
            "to": "c@x.org",
            "subject": "Proposta",
            "flags": ["\\Seen"],
            "date": "Tue, 14 Oct 2026 10:00:00 -0300",
            "message_id": "<s2@x>",
        },
    ]
    search = Mock(side_effect=lambda imap, folder, limit, text: [dict(m) for m in sent])
    monkeypatch.setattr("mailgrant.web.api.imap_search", search)
    audit.record("hermes", "send", mailbox="alpha", to=["ana@x.org"], message_id="<s3@x>")
    audit.record("lucas", "send", mailbox="alpha", to=["c@x.org"], message_id="<s2@x>")
    rows = web_client.get("/app/api/inbox?view=sent&mailbox=alpha").json()["messages"]
    assert [(r["uid"], r["folder"], r["to"], r["sent_by"], r["by_you"]) for r in rows] == [
        ("3", "Sent", ["Ana", "b@x.org"], "hermes", False),
        ("2", "Sent", ["c@x.org"], None, True),
    ]
    assert search.call_args.kwargs["folder"] == "Sent"


# ── HTML mail ───────────────────────────────────────────────────────────────

HTML_RECEIPT = '<table width="600"><tr><td style="color:#00a650">R$ 9,90</td></tr></table>'


def test_frame_endpoint_has_its_own_strict_headers(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(web_client, monkeypatch)
    msg = EmailMessage()
    msg.set_content("texto")
    msg.add_alternative(HTML_RECEIPT, subtype="html")
    fetch = Mock(return_value=email.message_from_bytes(msg.as_bytes()))
    monkeypatch.setattr("mailgrant.web.api.fetch_raw", fetch)
    r = web_client.get("/app/api/messages/alpha/7/html?folder=INBOX")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["content-security-policy"] == html_view.policy(images=False)
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "R$ 9,90" in r.text and "<title>" not in r.text
    assert fetch.call_args.kwargs == {"folder": "INBOX"}
    r = web_client.get("/app/api/messages/alpha/7/html?images=1")
    assert "https:" in r.headers["content-security-policy"]

    plain = EmailMessage()
    plain.set_content("só texto")
    fetch.return_value = email.message_from_bytes(plain.as_bytes())
    assert web_client.get("/app/api/messages/alpha/7/html").status_code == 404
    assert web_client.get("/app/api/messages/nope/7/html").status_code in (403, 404)


def test_app_pages_may_frame_only_themselves(web_client: TestClient) -> None:
    r = web_client.get("/app/")
    assert "frame-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
