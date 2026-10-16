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
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .. import __version__, audit
from ..config import Config
from .api import agent_send_notifier, build_router
from .push import Pusher
from .store import Store
from .watcher import Watcher

log = logging.getLogger("mailgrant.web")

STATIC = Path(__file__).parent / "static"

# Attachments always download and HTML mail is shown in a sandboxed frame from
# our own origin (with its own, stricter policy, see html_view), so the app
# needs nothing from other origins: no inline script, no CDNs.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; manifest-src 'self'; worker-src 'self'; "
    "frame-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; "
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
                # A route that set one of these (the mail frame) keeps its own.
                present = {k.lower() for k, _ in headers}
                defaults = [
                    (b"content-security-policy", CSP.encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-frame-options", b"DENY"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                ]
                if str(scope.get("path", "")).startswith("/app/api"):
                    defaults.append((b"cache-control", b"no-store"))
                elif str(scope.get("path", "")).startswith("/app/static/"):
                    # Without it browsers guess how long to keep a file, and a
                    # deploy can pair new JavaScript with yesterday's CSS.
                    defaults.append((b"cache-control", b"no-cache"))
                headers += [(k, v) for k, v in defaults if k not in present]
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
    # The shell names its CSS and JS with the version, so a new release is
    # always fetched as a whole, never half from an old cache.
    shell = (STATIC / "index.html").read_text()
    for asset in ("/app/static/app.css", "/app/static/app.js"):
        shell = shell.replace(f'"{asset}"', f'"{asset}?v={__version__}"')

    def index() -> HTMLResponse:
        return HTMLResponse(shell, headers={"cache-control": "no-cache"})

    app.add_api_route("/app/", index, include_in_schema=False)
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
