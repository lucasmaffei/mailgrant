"""CLI entrypoint.

mailgrant http    run the HTTP API, which also serves MCP under /mcp
mailgrant token   mint a bearer token and the sha256 to put in the config
mailgrant check   validate a config and print who may touch what
"""

from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mailgrant")
    parser.add_argument("--version", action="version", version=f"mailgrant {__version__}")
    sub = parser.add_subparsers(dest="mode", required=True)

    p_http = sub.add_parser(
        "http",
        help="Run the FastAPI HTTP server (also serves MCP under /mcp)",
    )
    p_http.add_argument("--host", default="127.0.0.1")
    p_http.add_argument("--port", type=int, default=8000)
    p_http.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS", "1")))
    p_http.add_argument("--config", help="Path to config.yaml (overrides MAILGRANT_CONFIG)")

    p_token = sub.add_parser("token", help="Mint a bearer token and its sha256 for the config")
    p_token.add_argument("--name", default="my-agent", help="Agent name for the YAML snippet")

    p_check = sub.add_parser("check", help="Validate the config and print the access matrix")
    p_check.add_argument("--config", help="Path to config.yaml (overrides MAILGRANT_CONFIG)")

    p_invite = sub.add_parser("invite", help="Print a one-time link to register a web passkey")
    p_invite.add_argument("--config", help="Path to config.yaml (overrides MAILGRANT_CONFIG)")
    p_invite.add_argument("--minutes", type=int, default=30, help="How long the link works")

    args = parser.parse_args(argv)

    if getattr(args, "config", None):
        os.environ["MAILGRANT_CONFIG"] = args.config

    if args.mode == "token":
        return _token(args.name)

    if args.mode == "check":
        return _check(args.config)

    if args.mode == "invite":
        return _invite(args.config, args.minutes)

    if args.mode == "http":
        import uvicorn

        uvicorn.run(
            "mailgrant.server:create_app",
            host=args.host,
            port=args.port,
            workers=args.workers,
            factory=True,
        )
        return 0

    parser.error(f"unknown mode: {args.mode}")
    return 2


def _token(name: str) -> int:
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    print(f"token (give this to the agent, shown once):\n  {token}\n")
    print("config entry (only the hash is stored):")
    print(f"  - name: {name}")
    print(f'    token_sha256: "{digest}"')
    print('    mailboxes: ["*"]          # or a list of names / addresses')
    print("    scopes: [read]            # read | mark | delete | send")
    return 0


def _check(path: str | None) -> int:
    from .config import ConfigError, load_config
    from .grants import _principal_for_agent

    try:
        cfg = load_config(path)
    except ConfigError as e:
        print(f"invalid: {e}", file=sys.stderr)
        return 1
    print(f"ok: {len(cfg.mailboxes)} mailbox(es), {len(cfg.agents)} agent(s)")
    if cfg.auth.tokens:
        print(f"warning: {len(cfg.auth.tokens)} legacy auth.tokens with full access to everything")
    for i, agent in enumerate(cfg.agents):
        p = _principal_for_agent(cfg, i)
        boxes = "all mailboxes" if p.mailboxes is None else ", ".join(sorted(p.mailboxes))
        print(f"  {agent.name:<20} [{', '.join(sorted(p.scopes))}]  {boxes}")
    if cfg.web is not None and cfg.web.enabled:
        from .grants import web_principal

        p = web_principal(cfg)
        boxes = "all mailboxes" if p.mailboxes is None else ", ".join(sorted(p.mailboxes))
        print(
            f"web app: on at {cfg.web.origin}/app for {p.name} [{', '.join(sorted(p.scopes))}]"
            f"  {boxes}; data in {cfg.web.data_dir}"
        )
        if cfg.web.manage:
            print(
                "manage: on — mailboxes and agents are managed in the web app; after the "
                "first start, the ones in this file are ignored"
            )
        if cfg.web.setup_code:
            print("setup code: set (creates the first passkey; ignored once one exists)")
    else:
        print("web app: off (no `web:` section)")
    for m in cfg.mailboxes:
        if m.imap is not None and m.smtp is not None and not m.smtp.save_copy_to:
            print(f"note: {m.name}: sent mail is not copied to IMAP (smtp.save_copy_to unset)")
    return 0


def _invite(path: str | None, minutes: int) -> int:
    from datetime import timedelta

    from .config import ConfigError, load_config

    try:
        cfg = load_config(path)
    except ConfigError as e:
        print(f"invalid: {e}", file=sys.stderr)
        return 1
    if not cfg.web_enabled or cfg.web is None:
        print("the web app is off: add a `web:` section to the config first", file=sys.stderr)
        return 1
    from .web.store import Store

    token = Store(cfg.web.data_dir).create_invite(timedelta(minutes=max(1, minutes)))
    print(f"Open on the device that will hold the passkey (valid {minutes} min, one use):")
    print(f"  {cfg.web.origin}/app/#/invite/{token}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
