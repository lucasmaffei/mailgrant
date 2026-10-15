"""web.manage: mailboxes and agents live in the database and change without a restart."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from mailgrant import audit
from mailgrant.config import load_config
from mailgrant.server import create_app

ORIGIN = "https://mail.example.org"
H = {"X-Mailgrant": "1", "Origin": ORIGIN}
HERMES = "EXAMPLE-hermes-token"


def write_config(tmp_path: Path, extra_mailbox: str = "") -> str:
    body = f"""
agents:
  - {{name: hermes, token: "{HERMES}", mailboxes: ["*"], scopes: [read, send]}}
mailboxes:
  - name: alpha
    imap: {{host: mail.invalid, username: alpha@example.org, password: secret-a}}
    smtp: {{host: mail.invalid, username: alpha@example.org, password: secret-a,
      from_address: alpha@example.org}}
  - name: beta
    imap: {{host: mail.invalid, username: beta@example.org, password: secret-b}}
{extra_mailbox}
web:
  origin: {ORIGIN}
  data_dir: {tmp_path / "data"}
  poll_seconds: 3600
  manage: true
  user: {{name: lucas, mailboxes: ["*"], scopes: [read, mark, delete, send]}}
"""
    p = tmp_path / "config.yaml"
    p.write_text(body)
    return str(p)


def client_for(path: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("mailgrant.web.watcher.Watcher.start", lambda self: False)
    return TestClient(create_app(load_config(path)), base_url=ORIGIN)


def sign_in(client: TestClient, monkeypatch: pytest.MonkeyPatch, confirm: bool = True) -> None:
    from datetime import timedelta

    store = client.app.state.web_store  # type: ignore[attr-defined]
    monkeypatch.setattr(
        "mailgrant.web.api.verify_registration_response",
        Mock(
            return_value=SimpleNamespace(
                credential_id=b"cred-1", credential_public_key=b"pk", sign_count=0
            )
        ),
    )
    invite = store.create_invite(timedelta(minutes=5))
    opts = client.post("/app/api/auth/register/options", headers=H, json={"invite": invite})
    client.post(
        "/app/api/auth/register/verify",
        headers=H,
        json={"challenge_id": opts.json()["challenge_id"], "name": "x", "credential": {}},
    )
    if confirm:
        store.confirm_session(client.cookies.get("mg_session"))


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MAILGRANT_SECRET_KEY", "test-key-for-mailgrant")
    yield
    audit.clear_sinks()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_first_start_imports_the_config_and_later_starts_ignore_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_config(tmp_path)
    with client_for(path, monkeypatch) as c:
        assert c.get("/whoami", headers=bearer(HERMES)).json()["agent"] == "hermes"
        names = [m["name"] for m in c.get("/mailboxes", headers=bearer(HERMES)).json()["mailboxes"]]
        assert names == ["alpha", "beta"]
    db = sqlite3.connect(tmp_path / "data" / "mailgrant.db")
    raw = " ".join(r[0] for r in db.execute("SELECT data FROM managed_mailboxes"))
    agents = " ".join(r[0] for r in db.execute("SELECT data FROM managed_agents"))
    assert "secret-a" not in raw and "enc:" in raw  # passwords are encrypted
    assert HERMES not in agents  # only the token's hash is kept
    # The file grows a mailbox; the database still decides.
    extra = (
        "  - name: gamma\n    imap: {host: mail.invalid, username: g@example.org, password: g}\n"
    )
    with client_for(write_config(tmp_path, extra), monkeypatch) as c:
        names = [m["name"] for m in c.get("/mailboxes", headers=bearer(HERMES)).json()["mailboxes"]]
        assert names == ["alpha", "beta"]


def test_changes_need_a_fresh_passkey_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with client_for(write_config(tmp_path), monkeypatch) as c:
        sign_in(c, monkeypatch, confirm=False)
        assert c.get("/app/api/admin/agents").status_code == 200  # reading is fine
        body = {"name": "vigo", "mailboxes": ["alpha"], "scopes": ["read"]}
        r = c.post("/app/api/admin/agents", headers=H, json=body)
        assert r.status_code == 403 and r.json()["detail"] == "confirm"
        assert c.get("/app/api/admin/export").status_code == 403
        assert c.post("/app/api/admin/agents", json=body).status_code == 403  # no CSRF header


def test_agents_are_created_changed_rotated_and_removed_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with client_for(write_config(tmp_path), monkeypatch) as c:
        sign_in(c, monkeypatch)
        r = c.post(
            "/app/api/admin/agents",
            headers=H,
            json={
                "name": "vigo",
                "description": "leitor",
                "mailboxes": ["alpha"],
                "scopes": ["read"],
            },
        )
        assert r.status_code == 200, r.text
        token = r.json()["token"]
        assert token.startswith("mg_") and r.json()["mcp_url"] == f"{ORIGIN}/mcp"
        me = c.get("/whoami", headers=bearer(token)).json()
        assert me["agent"] == "vigo" and me["scopes"] == ["read"] and me["mailboxes"] == ["alpha"]

        r = c.put(
            "/app/api/admin/agents/vigo",
            headers=H,
            json={"description": "leitor", "mailboxes": ["*"], "scopes": ["read", "mark"]},
        )
        assert r.status_code == 200, r.text
        me = c.get("/whoami", headers=bearer(token)).json()
        assert me["scopes"] == ["mark", "read"] and me["all_mailboxes"] is True

        new = c.post("/app/api/admin/agents/vigo/token", headers=H).json()["token"]
        assert c.get("/whoami", headers=bearer(token)).status_code == 401
        assert c.get("/whoami", headers=bearer(new)).json()["agent"] == "vigo"

        bad = c.put(
            "/app/api/admin/agents/vigo",
            headers=H,
            json={"mailboxes": ["ghost"], "scopes": ["read"]},
        )
        assert bad.status_code == 422 and "ghost" in bad.json()["detail"]

        assert c.delete("/app/api/admin/agents/vigo", headers=H).status_code == 200
        assert c.get("/whoami", headers=bearer(new)).status_code == 401


def test_mailboxes_keep_passwords_and_refuse_breaking_deletes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with client_for(write_config(tmp_path), monkeypatch) as c:
        sign_in(c, monkeypatch)
        new = {
            "name": "gamma",
            "imap": {
                "host": "mail.invalid",
                "port": 993,
                "tls": "ssl",
                "username": "g@example.org",
                "password": "pw-g",
            },
        }
        r = c.post("/app/api/admin/mailboxes", headers=H, json=new)
        assert r.status_code == 200, r.text
        listed = c.get("/app/api/admin/mailboxes").json()["mailboxes"]
        gamma = next(m for m in listed if m["name"] == "gamma")
        assert gamma["imap"]["has_password"] and "password" not in gamma["imap"]
        assert gamma["agents"] == ["hermes"]  # through "*"
        # Editing without a password keeps the saved one.
        edit = {"imap": {**new["imap"], "password": "", "port": 1993}}
        assert c.put("/app/api/admin/mailboxes/gamma", headers=H, json=edit).status_code == 200
        cfg = c.app.state.web_store  # noqa: F841 - the live config is what agents see
        mb = next(
            m
            for m in c.get("/mailboxes", headers=bearer(HERMES)).json()["mailboxes"]
            if m["name"] == "gamma"
        )
        assert mb["imap"] is True
        export = c.get("/app/api/admin/export")
        assert export.status_code == 200 and "pw-g" in export.text and "port: 1993" in export.text
        # A mailbox named in an agent's list can't vanish under it.
        c.post(
            "/app/api/admin/agents",
            headers=H,
            json={"name": "vigo", "mailboxes": ["gamma"], "scopes": ["read"]},
        )
        r = c.delete("/app/api/admin/mailboxes/gamma", headers=H)
        assert r.status_code == 422 and "vigo" in r.json()["detail"]
        missing = {"name": "delta", "imap": {"host": "h", "username": "d@x.org", "password": ""}}
        assert c.post("/app/api/admin/mailboxes", headers=H, json=missing).status_code == 422


def test_other_workers_pick_up_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write_config(tmp_path)
    with client_for(path, monkeypatch) as a, client_for(path, monkeypatch) as b:
        sign_in(a, monkeypatch)
        token = a.post(
            "/app/api/admin/agents",
            headers=H,
            json={"name": "vigo", "mailboxes": ["alpha"], "scopes": ["read"]},
        ).json()["token"]
        # The other "worker" checks at most once a second; skip the wait.
        monkeypatch.setattr("mailgrant.web.managed.time.monotonic", lambda: 10**9)
        assert b.get("/whoami", headers=bearer(token)).json()["agent"] == "vigo"


def test_connection_test_uses_saved_passwords(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = {}
    monkeypatch.setattr(
        "mailgrant.web.admin.imap_check", lambda conf: seen.setdefault("imap", conf) and ["INBOX"]
    )

    def smtp_fail(conf):
        raise __import__("mailgrant.smtp_client", fromlist=["SmtpError"]).SmtpError("535 bad auth")

    monkeypatch.setattr("mailgrant.web.admin.smtp_check", smtp_fail)
    with client_for(write_config(tmp_path), monkeypatch) as c:
        sign_in(c, monkeypatch)
        r = c.post(
            "/app/api/admin/mailboxes/test",
            headers=H,
            json={
                "name": "alpha",
                "imap": {"host": "mail.invalid", "username": "alpha@example.org", "password": ""},
                "smtp": {
                    "host": "mail.invalid",
                    "username": "alpha@example.org",
                    "password": "",
                    "from_address": "alpha@example.org",
                },
            },
        ).json()
        assert r["imap"]["ok"] is True and seen["imap"].password == "secret-a"
        assert r["smtp"] == {"ok": False, "error": "535 bad auth"}
