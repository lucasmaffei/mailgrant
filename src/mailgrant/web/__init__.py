"""Optional web app: inbox, agent activity and push, as an installable PWA.

Enabled by a `web:` section in the config. Without it none of this is
imported at request time, no database is created and no extra route exists:
mailgrant stays a stateless MCP/REST gateway.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .. import audit
from ..config import Config
from .api import agent_send_notifier, build_router
from .push import Pusher
from .store import Store
from .watcher import Watcher

log = logging.getLogger("mailgrant.web")

STATIC = Path(__file__).parent / "static"

# Message bodies are rendered as text and attachments always download, so the
# app needs nothing from other origins: no inline script, no frames, no CDNs.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; manifest-src 'self'; worker-src 'self'; "
    "frame-src 'none'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'"
)


class _AppHeaders:
    """Security headers on everything under /app."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not str(scope.get("path", "")).startswith("/app"):
            await self._app(scope, receive, send)
            return

        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers += [
                    (b"content-security-policy", CSP.encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-frame-options", b"DENY"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                ]
                if str(scope.get("path", "")).startswith("/app/api"):
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        await self._app(scope, receive, with_headers)


def mount(app: FastAPI, cfg: Config) -> tuple[Callable[[], None], Callable[[], None]]:
    """Attach the web app to `app`; returns (start, stop) for the lifespan."""
    assert cfg.web is not None
    store = Store(cfg.web.data_dir)
    managed = None
    if cfg.managed:
        from .managed import Managed

        managed = Managed(cfg, store)
        managed.bootstrap()
    pusher = Pusher(store, cfg.web.push_contact or cfg.web.origin)
    watcher = Watcher(cfg, store, pusher)

    app.include_router(build_router(cfg, store, pusher, managed))
    app.add_middleware(_AppHeaders)

    def page(name: str, media_type: str | None = None, **headers: str):
        def handler() -> FileResponse:
            return FileResponse(
                STATIC / name,
                media_type=media_type,
                headers={"cache-control": "no-cache", **headers},
            )

        return handler

    app.add_api_route("/", lambda: RedirectResponse("/app/"), include_in_schema=False)
    app.add_api_route("/app", lambda: RedirectResponse("/app/"), include_in_schema=False)
    app.add_api_route("/app/", page("index.html"), include_in_schema=False)
    # The worker sits at /app/ so its scope covers the whole app.
    app.add_api_route("/app/sw.js", page("sw.js", "text/javascript"), include_in_schema=False)
    app.add_api_route(
        "/app/manifest.webmanifest",
        page("manifest.webmanifest", "application/manifest+json"),
        include_in_schema=False,
    )
    app.mount("/app/static", StaticFiles(directory=STATIC), name="app-static")

    def start() -> None:
        audit.add_sink(agent_send_notifier(cfg, store, pusher))
        if watcher.start():
            log.info(
                "web: watching %d mailbox(es) every %ds", len(watcher.mailboxes()), watcher.interval
            )

    def stop() -> None:
        watcher.stop()
        audit.clear_sinks()

    app.state.web_store = store
    app.state.web_watcher = watcher
    return start, stop
