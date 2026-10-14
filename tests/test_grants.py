"""Per-agent grants: who sees which mailbox, with which scopes, over HTTP and MCP."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from mailgrant.config import ConfigError, load_config
from mailgrant.grants import authenticate
from mailgrant.server import create_app

READER = "EXAMPLE-reader-token"
SENDER = "EXAMPLE-sender-token"
ADMIN = "EXAMPLE-admin-token"
HASHED = "EXAMPLE-hashed-token"
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}

CONFIG = f"""
auth:
  tokens: ["{ADMIN}"]
agents:
  - name: reader
    token: "{READER}"
    mailboxes: [alpha]
    scopes: [read]
  - name: sender
    token: "{SENDER}"
    mailboxes: ["beta@example.org", gamma]
    scopes: [read, send, mark]
  - name: hashed
    token_sha256: "sha256:{hashlib.sha256(HASHED.encode()).hexdigest().upper()}"
    mailboxes: ["*"]
    scopes: [read, delete]
mailboxes:
  - name: alpha
    imap: {{host: mail.invalid, username: alpha@example.org, password: a}}
    smtp: {{host: mail.invalid, username: alpha@example.org, password: a,
      from_address: alpha@example.org}}
  - name: beta
    imap: {{host: mail.invalid, username: beta@example.org, password: b}}
    smtp: {{host: mail.invalid, username: beta@example.org, password: b,
      from_address: "Beta <beta@example.org>", allowed_from: [sales@example.org],
      save_copy_to: Sent}}
  - name: gamma
    imap: {{host: mail.invalid, username: gamma@example.org, password: c}}
"""


def _write(tmp_path: Path, body: str) -> str:
    p = tmp_path / "config.yaml"
    p.write_text(body)
    return str(p)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    with TestClient(create_app(load_config(_write(tmp_path, CONFIG)))) as c:
        yield c


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _mcp(client: TestClient, token: str, method: str, params: dict[str, Any]) -> Any:
    response = client.post(
        "/mcp",
        headers={**MCP_HEADERS, **_h(token)},
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )
    assert response.status_code == 200, response.text
    if response.headers["content-type"].startswith("application/json"):
        payload = response.json()
    else:
        line = next(x for x in response.text.splitlines() if x.startswith("data: "))
        payload = json.loads(line.removeprefix("data: "))
    return payload["result"]


def _tool(client: TestClient, token: str, name: str, **arguments: Any) -> Any:
    result = _mcp(client, token, "tools/call", {"name": name, "arguments": arguments})
    return json.loads(result["content"][0]["text"])


# ── config ──────────────────────────────────────────────────────────────────


def test_digest_is_normalised(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, CONFIG))
    digest = cfg.agents[2].token_sha256
    assert digest == hashlib.sha256(HASHED.encode()).hexdigest()


@pytest.mark.parametrize(
    "agent,needle",
    [
        ("{name: x, mailboxes: [alpha], scopes: [read]}", "exactly one"),
        (
            "{name: x, token: t, token_sha256: "
            + "a" * 64
            + ", mailboxes: [alpha], scopes: [read]}",
            "exactly one",
        ),
        ("{name: x, token: t, mailboxes: [nope], scopes: [read]}", "unknown mailbox"),
        ("{name: x, token: t, mailboxes: [alpha], scopes: [write]}", "scopes"),
        ("{name: x, token: t, mailboxes: [], scopes: [read]}", "mailboxes"),
        ("{name: 'bad name', token: t, mailboxes: [alpha], scopes: [read]}", "invalid"),
        ("{name: x, token_sha256: abc, mailboxes: [alpha], scopes: [read]}", "64 hex"),
    ],
)
def test_bad_agents_are_rejected(tmp_path: Path, agent: str, needle: str) -> None:
    body = f"""
agents:
  - {agent}
mailboxes:
  - name: alpha
    imap: {{host: h, username: alpha@example.org, password: p}}
"""
    with pytest.raises(ConfigError, match=needle):
        load_config(_write(tmp_path, body))


def test_duplicate_tokens_are_rejected(tmp_path: Path) -> None:
    body = """
auth: {tokens: [same]}
agents:
  - {name: x, token: same, mailboxes: [alpha], scopes: [read]}
mailboxes:
  - name: alpha
    imap: {host: h, username: u, password: p}
"""
    with pytest.raises(ConfigError, match="more than once"):
        load_config(_write(tmp_path, body))


def test_save_copy_needs_imap(tmp_path: Path) -> None:
    body = """
mailboxes:
  - name: alpha
    smtp: {host: h, username: u, password: p, from_address: u@x, save_copy_to: Sent}
"""
    with pytest.raises(ConfigError, match="save_copy_to"):
        load_config(_write(tmp_path, body))


def test_env_references_are_expanded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MG_PASS", "s3cret")
    monkeypatch.setenv("MG_TOKEN", "tok")
    body = """
agents:
  - {name: x, token: "${MG_TOKEN}", mailboxes: ["*"], scopes: [read]}
mailboxes:
  - name: alpha
    imap: {host: h, username: u, password: "pre-${MG_PASS}"}
"""
    cfg = load_config(_write(tmp_path, body))
    assert cfg.mailboxes[0].imap is not None
    assert cfg.mailboxes[0].imap.password == "pre-s3cret"
    assert cfg.agents[0].token == "tok"


def test_missing_env_reference_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MG_NOPE", raising=False)
    body = """
mailboxes:
  - name: alpha
    imap: {host: h, username: u, password: "${MG_NOPE}"}
"""
    with pytest.raises(ConfigError, match="MG_NOPE"):
        load_config(_write(tmp_path, body))


# ── authentication ──────────────────────────────────────────────────────────


def test_authenticate_maps_tokens_to_principals(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, CONFIG))
    reader = authenticate(cfg, READER)
    assert reader is not None and reader.name == "reader"
    assert reader.mailboxes == frozenset({"alpha"})
    sender = authenticate(cfg, SENDER)
    assert sender is not None and sender.mailboxes == frozenset({"beta", "gamma"})
    hashed = authenticate(cfg, HASHED)
    assert hashed is not None and hashed.mailboxes is None
    admin = authenticate(cfg, ADMIN)
    assert admin is not None and admin.has("send") and admin.mailboxes is None
    assert authenticate(cfg, "wrong") is None
    assert authenticate(cfg, "") is None


# ── HTTP ────────────────────────────────────────────────────────────────────


def test_mailboxes_and_whoami_show_only_the_grant(client: TestClient) -> None:
    names = [m["name"] for m in client.get("/mailboxes", headers=_h(READER)).json()["mailboxes"]]
    assert names == ["alpha"]
    who = client.get("/whoami", headers=_h(SENDER)).json()
    assert who == {
        "agent": "sender",
        "scopes": ["mark", "read", "send"],
        "mailboxes": ["beta", "gamma"],
        "all_mailboxes": False,
    }


def test_mailbox_outside_grant_is_indistinguishable_from_unknown(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetch = Mock(return_value={})
    monkeypatch.setattr("mailgrant.server.imap_fetch", fetch)
    outside = client.get("/mailboxes/beta/messages/1", headers=_h(READER))
    unknown = client.get("/mailboxes/nope/messages/1", headers=_h(READER))
    assert outside.status_code == unknown.status_code == 404
    fetch.assert_not_called()


def test_missing_scope_is_403(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    delete = Mock(return_value={"ok": True})
    monkeypatch.setattr("mailgrant.server.imap_delete", delete)
    r = client.delete("/mailboxes/alpha/messages/1", headers=_h(READER))
    assert r.status_code == 403
    assert "delete" in r.json()["detail"]
    delete.assert_not_called()


def test_inbox_fans_out_only_over_the_grant(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    search = Mock(return_value={"messages": [], "errors": []})
    monkeypatch.setattr("mailgrant.server.imap_unified_search", search)
    assert client.get("/inbox", headers=_h(SENDER)).status_code == 200
    assert [m.name for m in search.call_args.args[0]] == ["beta", "gamma"]
    # Filtering by a mailbox outside the grant finds nothing rather than leaking it.
    assert client.get("/inbox?mailbox=alpha", headers=_h(SENDER)).status_code == 404


def test_send_refuses_foreign_from_and_allows_aliases(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    send = Mock(return_value={"message_id": "<m@x>"})
    monkeypatch.setattr("mailgrant.server.smtp_send", send)
    body = {"to": ["x@example.com"], "subject": "s", "body_text": "b"}

    spoof = client.post(
        "/mailboxes/beta/send", headers=_h(SENDER), json={**body, "from_address": "ceo@corp.com"}
    )
    assert spoof.status_code == 403
    send.assert_not_called()

    alias = client.post(
        "/mailboxes/beta/send",
        headers=_h(SENDER),
        json={**body, "from_address": "Sales <sales@example.org>", "in_reply_to": "<p@x>"},
    )
    assert alias.status_code == 200
    kwargs = send.call_args.kwargs
    assert kwargs["in_reply_to"] == "<p@x>"
    imap, folder = kwargs["copy_to"]
    assert folder == "Sent" and imap.username == "beta@example.org"


def test_audit_log_records_allowed_and_denied(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("mailgrant.server.imap_fetch", Mock(return_value={}))
    with caplog.at_level(logging.INFO, logger="mailgrant.audit"):
        client.get("/mailboxes/alpha/messages/7", headers=_h(READER))
        client.get("/mailboxes/beta/messages/8", headers=_h(READER))
    entries = [json.loads(r.getMessage()) for r in caplog.records if r.name == "mailgrant.audit"]
    assert {"agent": "reader", "action": "get_message", "mailbox": "alpha", "uid": "7"}.items() <= (
        entries[-2].items()
    )
    assert entries[-2]["outcome"] == "ok"
    assert entries[-1]["outcome"] == "denied" and entries[-1]["reason"] == "not_found"


# ── MCP ─────────────────────────────────────────────────────────────────────


def test_tools_list_hides_tools_outside_scopes(client: TestClient) -> None:
    def names(token: str) -> set[str]:
        return {t["name"] for t in _mcp(client, token, "tools/list", {})["tools"]}

    assert names(READER) == {
        "whoami",
        "mailboxes",
        "inbox",
        "list_folders",
        "list_messages",
        "search",
        "get_message",
    }
    assert {"send", "mark_seen"} <= names(SENDER) and "delete_message" not in names(SENDER)
    assert "delete_message" in names(HASHED) and "send" not in names(HASHED)


def test_mcp_enforces_grant_even_for_hidden_tools(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    delete = Mock(return_value={"ok": True})
    fetch = Mock(return_value={"uid": "1"})
    monkeypatch.setattr("mailgrant.mcp_server.imap_delete", delete)
    monkeypatch.setattr("mailgrant.mcp_server.imap_fetch", fetch)

    denied = _tool(client, READER, "delete_message", mailbox="alpha", uid="1")
    assert "lacks the 'delete' scope" in denied["error"]
    delete.assert_not_called()

    hidden = _tool(client, READER, "get_message", mailbox="beta@example.org", uid="1")
    assert "unknown mailbox" in hidden["error"]
    fetch.assert_not_called()

    assert _tool(client, READER, "get_message", mailbox="alpha", uid="1") == {"uid": "1"}


def test_mcp_whoami_and_mailboxes(client: TestClient) -> None:
    assert _tool(client, HASHED, "whoami")["all_mailboxes"] is True
    listed = _tool(client, SENDER, "mailboxes")["mailboxes"]
    assert [m["name"] for m in listed] == ["beta", "gamma"]


def test_config_can_come_from_an_environment_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAILGRANT_CONFIG_YAML", CONFIG)
    monkeypatch.setenv("MAILGRANT_CONFIG", str(tmp_path / "missing.yaml"))
    assert [m.name for m in load_config().mailboxes] == ["alpha", "beta", "gamma"]
    # An explicit path still wins over the variable.
    other = _write(tmp_path, "mailboxes: []\n")
    assert load_config(other).mailboxes == []


def test_same_token_as_plaintext_and_hash_is_rejected(tmp_path: Path) -> None:
    digest = hashlib.sha256(b"shared").hexdigest()
    body = f"""
agents:
  - {{name: a, token: shared, mailboxes: [alpha], scopes: [read]}}
  - {{name: b, token_sha256: "{digest}", mailboxes: [alpha], scopes: [send]}}
mailboxes:
  - name: alpha
    imap: {{host: h, username: u, password: p}}
"""
    with pytest.raises(ConfigError, match="more than once"):
        load_config(_write(tmp_path, body))


def test_config_can_come_base64_encoded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import base64

    monkeypatch.setenv("MAILGRANT_CONFIG_B64", base64.b64encode(CONFIG.encode()).decode())
    monkeypatch.setenv("MAILGRANT_CONFIG_YAML", "mailboxes: []\n")  # B64 wins
    assert [m.name for m in load_config().mailboxes] == ["alpha", "beta", "gamma"]
    monkeypatch.setenv("MAILGRANT_CONFIG_B64", "not base64!")
    with pytest.raises(ConfigError, match="MAILGRANT_CONFIG_B64"):
        load_config()
