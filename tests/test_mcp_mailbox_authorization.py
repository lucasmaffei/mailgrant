"""Mailbox selection and credential forwarding through the production MCP route."""

import json
from http import HTTPStatus
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from mailgrant.config import load_config
from mailgrant.server import create_app

TOKENS = ["EXAMPLE-DO-NOT-USE-primary", "EXAMPLE-DO-NOT-USE-secondary"]
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}
SELECTORS = [
    pytest.param("alpha", "alpha", id="alpha-name"),
    pytest.param("alpha@example.org", "alpha", id="alpha-address"),
    pytest.param("beta", "beta", id="beta-name"),
    pytest.param("beta@example.org", "beta", id="beta-address"),
]
OPERATIONS = [
    pytest.param("get_message", "imap_fetch", {"uid": "42"}, id="read"),
    pytest.param("delete_message", "imap_delete", {"uid": "42"}, id="delete"),
    pytest.param(
        "send",
        "smtp_send",
        {"to": ["recipient@example.org"], "subject": "test", "body_text": "test"},
        id="send",
    ),
]
EMPTY_AUTH = [
    pytest.param(None, id="auth-omitted"),
    pytest.param({}, id="auth-empty"),
    pytest.param({"tokens": []}, id="tokens-empty"),
]
INVALID_HEADERS = [
    pytest.param({}, id="missing"),
    pytest.param({"Authorization": "Bearer EXAMPLE-DO-NOT-USE-wrong"}, id="wrong"),
    pytest.param({"Authorization": f"Basic {TOKENS[0]}"}, id="not-bearer"),
]
MAIL_RESULT = {"uid": "42", "subject": "test", "ok": True}
AUTH_ERROR = {"detail": "missing or invalid Bearer token"}


def _call(client, headers, tool, selector, arguments):
    return client.post(
        "/mcp",
        headers={**MCP_HEADERS, **headers},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": {"mailbox": selector, **arguments}},
        },
    )


def _result(response):
    assert response.status_code == HTTPStatus.OK, response.text
    if response.headers["content-type"].startswith("application/json"):
        payload = response.json()
    else:
        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert len(events) == 1
        payload = events[0]
    assert payload["id"] == 1
    assert "error" not in payload
    assert not payload["result"].get("isError", False)
    return json.loads(payload["result"]["content"][0]["text"])


def _boundary(monkeypatch, boundary):
    operation = Mock(return_value=MAIL_RESULT)
    monkeypatch.setattr(f"mailgrant.mcp_server.{boundary}", operation)
    return operation


def _assert_credentials(operation, boundary, mailbox):
    operation.assert_called_once()
    credentials = operation.call_args.args[0]
    assert credentials.host == "mail.invalid"
    assert credentials.username == f"{mailbox}@example.org"
    assert credentials.password == f"EXAMPLE-DO-NOT-USE-{mailbox}"
    if boundary == "smtp_send":
        assert credentials.from_address == f"{mailbox}@example.org"
        assert operation.call_args.args == (credentials,)
        assert operation.call_args.kwargs == {
            "to": ["recipient@example.org"],
            "subject": "test",
            "body_text": "test",
            "body_html": None,
            "cc": [],
            "bcc": [],
            "from_address": None,
            "reply_to": None,
            "in_reply_to": None,
            "references": None,
            "copy_to": None,
        }
        return
    assert operation.call_args.args == (credentials, "42")
    expected: dict[str, object] = {"folder": None}
    if boundary == "imap_fetch":
        expected["reader"] = False
    if boundary == "imap_delete":
        expected["permanent"] = False
    assert operation.call_args.kwargs == expected


@pytest.mark.parametrize("token", TOKENS)
@pytest.mark.parametrize("selector,mailbox", SELECTORS)
@pytest.mark.parametrize("tool,boundary,arguments", OPERATIONS)
def test_each_token_can_operate_on_either_mailbox_by_name_or_address(
    security_config_factory, monkeypatch, token, selector, mailbox, tool, boundary, arguments
):
    operation = _boundary(monkeypatch, boundary)
    config = load_config(str(security_config_factory({"tokens": TOKENS})))
    with TestClient(create_app(config)) as client:
        response = _call(client, {"Authorization": f"Bearer {token}"}, tool, selector, arguments)
    # The mocked boundary's return value passes straight through for every tool.
    assert _result(response) == MAIL_RESULT
    _assert_credentials(operation, boundary, mailbox)


@pytest.mark.parametrize("auth", EMPTY_AUTH)
@pytest.mark.parametrize("selector,mailbox", SELECTORS)
@pytest.mark.parametrize("tool,boundary,arguments", OPERATIONS)
def test_empty_auth_blocks_mcp_mail_operations(
    security_config_factory, monkeypatch, auth, selector, mailbox, tool, boundary, arguments
):
    operation = _boundary(monkeypatch, boundary)
    config = load_config(str(security_config_factory(auth)))
    with TestClient(create_app(config)) as client:
        response = _call(client, {}, tool, selector, arguments)
    if response.status_code == HTTPStatus.OK:
        assert _result(response) == MAIL_RESULT
        _assert_credentials(operation, boundary, mailbox)
    assert (
        response.status_code == HTTPStatus.UNAUTHORIZED
    ), f"Anonymous MCP {tool} admitted for {selector}; mail calls={operation.call_count}"
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == AUTH_ERROR
    operation.assert_not_called()


@pytest.mark.parametrize("headers", INVALID_HEADERS)
@pytest.mark.parametrize("selector,mailbox", SELECTORS)
@pytest.mark.parametrize("tool,boundary,arguments", OPERATIONS)
def test_invalid_auth_cannot_select_mailbox_credentials(
    security_config_factory, monkeypatch, headers, selector, mailbox, tool, boundary, arguments
):
    operation = _boundary(monkeypatch, boundary)
    config = load_config(str(security_config_factory({"tokens": TOKENS})))
    with TestClient(create_app(config)) as client:
        response = _call(client, headers, tool, selector, arguments)
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == AUTH_ERROR
    operation.assert_not_called()


@pytest.mark.parametrize("selector", ["unknown", ""])
@pytest.mark.parametrize("tool,boundary,arguments", OPERATIONS)
def test_invalid_selector_never_reaches_mail_service(
    security_config_factory, monkeypatch, selector, tool, boundary, arguments
):
    operation = _boundary(monkeypatch, boundary)
    config = load_config(str(security_config_factory({"tokens": TOKENS})))
    with TestClient(create_app(config)) as client:
        response = _call(
            client, {"Authorization": f"Bearer {TOKENS[0]}"}, tool, selector, arguments
        )
    expected = "unknown mailbox: 'unknown'" if selector else "`mailbox` is required"
    assert _result(response) == {"error": expected}
    operation.assert_not_called()
