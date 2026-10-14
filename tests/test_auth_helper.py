"""Bearer validation must reject unconfigured credentials as well as bad headers."""

from http import HTTPStatus

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from mailgrant.auth import check_bearer
from mailgrant.config import AuthConfig

TOKEN = "EXAMPLE-DO-NOT-USE"


@pytest.mark.parametrize("tokens", [[], [TOKEN]])
@pytest.mark.parametrize("header", [None, "", "Basic EXAMPLE-DO-NOT-USE", "Bearer wrong"])
def test_helper_rejects_missing_or_invalid_credentials(tokens, header):
    headers = [] if header is None else [(b"authorization", header.encode("ascii"))]
    request = Request({"type": "http", "headers": headers})
    with pytest.raises(HTTPException) as failure:
        check_bearer(AuthConfig(tokens=tokens), request)
    assert failure.value.status_code == HTTPStatus.UNAUTHORIZED
    assert failure.value.headers == {"WWW-Authenticate": "Bearer"}
    expected = (
        "invalid Bearer token" if header == "Bearer wrong" else "missing or malformed Bearer token"
    )
    assert failure.value.detail == expected


def test_helper_rejects_any_bearer_when_no_tokens_configured():
    request = Request({"type": "http", "headers": [(b"authorization", f"Bearer {TOKEN}".encode())]})
    with pytest.raises(HTTPException) as failure:
        check_bearer(AuthConfig(), request)
    assert failure.value.status_code == HTTPStatus.UNAUTHORIZED
    assert failure.value.detail == "invalid Bearer token"


def test_helper_accepts_configured_bearer():
    request = Request({"type": "http", "headers": [(b"authorization", f"Bearer {TOKEN}".encode())]})
    assert check_bearer(AuthConfig(tokens=[TOKEN]), request) is None
