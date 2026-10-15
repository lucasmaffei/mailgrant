"""Mailboxes and agents managed from the web app (`web.manage: true`).

The database becomes the source of truth for both lists. The first start
imports whatever the config file has; after that the file's `mailboxes` and
`agents` are ignored, and every change made in the app reaches all workers
without a restart: each request asks the database for its config version
(at most once a second) and reloads when another worker saved something.

Mailbox passwords are encrypted at rest with a key from MAILGRANT_SECRET_KEY,
or, without it, a random key kept in `data_dir/secret.key`. Agent tokens are
never stored, only their SHA-256, so a new token is shown once and lost.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable

import yaml
from cryptography.fernet import Fernet, InvalidToken
from pydantic import ValidationError

from ..config import ALL_MAILBOXES, AgentConfig, Config, MailboxConfig
from .store import Store, iso, now

log = logging.getLogger(__name__)

_SEALED = "enc:"
_PROTOCOLS = ("imap", "smtp")


class ManageError(ValueError):
    """A change that would leave the config invalid, said in plain words."""


def _fernet(data_dir: str) -> Fernet:
    raw = os.environ.get("MAILGRANT_SECRET_KEY", "").strip()
    if raw:
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()))
    path = Path(data_dir) / "secret.key"
    if not path.exists():
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(Fernet.generate_key())
            log.warning(
                "manage: MAILGRANT_SECRET_KEY is not set; mailbox passwords are encrypted "
                "with a key kept next to the database (%s)",
                path,
            )
        except FileExistsError:
            pass  # another worker created it first
    return Fernet(path.read_bytes().strip())


def _first_error(e: ValidationError) -> str:
    err = e.errors()[0]
    where = ".".join(str(p) for p in err.get("loc", ()) if p != "__root__")
    msg = str(err.get("msg", "invalid")).removeprefix("Value error, ")
    return f"{where}: {msg}" if where and not msg.startswith(where) else msg


def new_token() -> str:
    # Hex: a token pasted into chat or a terminal keeps every character.
    return "mg_" + secrets.token_hex(24)


class Managed:
    def __init__(self, cfg: Config, store: Store) -> None:
        assert cfg.web is not None
        self.cfg = cfg
        self.store = store
        self.fernet = _fernet(cfg.web.data_dir)
        # Everything except the two managed lists comes from the file.
        self.base = cfg.model_dump(exclude={"mailboxes", "agents"})
        self.version = -1
        self._checked = 0.0
        self._lock = threading.Lock()
        self.on_change: list[Callable[[], None]] = []

    # ── start-up and reloads ──────────────────────────────────────────────

    def bootstrap(self) -> None:
        if not self.store.get_pref("managed_imported"):
            self.store.managed_write(
                put={
                    "mailboxes": {m.name: self._seal(m) for m in self.cfg.mailboxes},
                    "agents": {a.name: self._agent_row(a) for a in self.cfg.agents},
                }
            )
            self.store.set_pref("managed_imported", iso(now()))
            log.info(
                "manage: imported %d mailbox(es) and %d agent(s) from the config",
                len(self.cfg.mailboxes),
                len(self.cfg.agents),
            )
        elif self.cfg.mailboxes or self.cfg.agents:
            log.warning(
                "manage: the web app manages mailboxes and agents; the %d mailbox(es) and "
                "%d agent(s) in the config file are ignored",
                len(self.cfg.mailboxes),
                len(self.cfg.agents),
            )
        self.load(force=True)
        self.cfg._refresh = self.refresh

    def refresh(self) -> None:
        if time.monotonic() - self._checked < 1.0:
            return
        self._checked = time.monotonic()
        try:
            self.load()
        except Exception:  # noqa: BLE001 - keep serving the last good config
            log.exception("manage: reload failed")

    def load(self, force: bool = False) -> None:
        version = self.store.config_version()
        if not force and version == self.version:
            return
        mailboxes = [self._open(r["data"]) for r in self.store.managed_rows("mailboxes")]
        agents = [self._agent(r["data"]) for r in self.store.managed_rows("agents")]
        fresh = self._validate(mailboxes, agents)
        self.cfg.mailboxes = fresh.mailboxes
        self.cfg.agents = fresh.agents
        self.version = version
        for hook in self.on_change:
            hook()

    # ── rows ──────────────────────────────────────────────────────────────

    def _seal(self, m: MailboxConfig) -> dict[str, Any]:
        data = m.model_dump()
        for proto in _PROTOCOLS:
            if data.get(proto):
                pw = data[proto]["password"]
                data[proto]["password"] = _SEALED + self.fernet.encrypt(pw.encode()).decode()
        return data

    def _open(self, raw: str) -> MailboxConfig:
        data = json.loads(raw)
        for proto in _PROTOCOLS:
            pw = (data.get(proto) or {}).get("password", "")
            if pw.startswith(_SEALED):
                try:
                    data[proto]["password"] = self.fernet.decrypt(pw[len(_SEALED) :]).decode()
                except InvalidToken as e:
                    raise ManageError(
                        f"cannot decrypt the password of {data.get('name')!r}: "
                        "MAILGRANT_SECRET_KEY changed?"
                    ) from e
        return MailboxConfig.model_validate(data)

    @staticmethod
    def _agent_row(a: AgentConfig, token_created_at: str | None = None) -> dict[str, Any]:
        digest = a.token_sha256 or hashlib.sha256((a.token or "").encode()).hexdigest()
        return {
            "name": a.name,
            "description": a.description,
            "token_sha256": digest,
            "mailboxes": list(a.mailboxes),
            "scopes": list(a.scopes),
            "token_created_at": token_created_at,
        }

    @staticmethod
    def _agent(raw: str) -> AgentConfig:
        data = json.loads(raw)
        data.pop("token_created_at", None)
        return AgentConfig.model_validate(data)

    def token_dates(self) -> dict[str, str | None]:
        return {
            r["name"]: json.loads(r["data"]).get("token_created_at")
            for r in self.store.managed_rows("agents")
        }

    def _validate(self, mailboxes: list[MailboxConfig], agents: list[AgentConfig]) -> Config:
        try:
            return Config.model_validate(
                {
                    **self.base,
                    "mailboxes": [m.model_dump() for m in mailboxes],
                    "agents": [a.model_dump(exclude_none=True) for a in agents],
                }
            )
        except ValidationError as e:
            raise ManageError(_first_error(e)) from e

    # ── changes ───────────────────────────────────────────────────────────

    def save_mailbox(self, data: dict[str, Any], existing: str | None) -> MailboxConfig:
        """Create (existing=None) or replace a mailbox. Blank passwords keep the saved ones."""
        with self._lock:
            self.load()
            old = self.cfg.get(existing) if existing else None
            if existing and old is None:
                raise ManageError(f"unknown mailbox {existing!r}")
            data = {**data, "name": existing or data.get("name")}
            for proto in _PROTOCOLS:
                part = data.get(proto)
                if part and not part.get("password"):
                    kept = getattr(old, proto, None) if old else None
                    if kept is None:
                        raise ManageError(f"{proto}: the password is required")
                    part["password"] = kept.password
            try:
                mb = MailboxConfig.model_validate(data)
            except ValidationError as e:
                raise ManageError(_first_error(e)) from e
            if not existing and self.cfg.get(mb.name) is not None:
                raise ManageError(f"there is already a mailbox named {mb.name!r}")
            mailboxes = [mb if m.name == mb.name else m for m in self.cfg.mailboxes]
            if not existing:
                mailboxes.append(mb)
            self._validate(mailboxes, self.cfg.agents)
            self.store.managed_write(put={"mailboxes": {mb.name: self._seal(mb)}})
            self.load(force=True)
            return mb

    def delete_mailbox(self, name: str) -> None:
        with self._lock:
            self.load()
            if self.cfg.get(name) is None:
                raise ManageError(f"unknown mailbox {name!r}")
            users = [
                a.name
                for a in self.cfg.agents
                if any(
                    (m := self.cfg.find(ref)) is not None and m.name == name for ref in a.mailboxes
                )
            ]
            if users:
                raise ManageError(
                    f"{name!r} is in the permissions of {', '.join(users)}; take it out there first"
                )
            assert self.cfg.web is not None
            if name in self.cfg.web.user.mailboxes:
                raise ManageError(f"{name!r} is listed in web.user.mailboxes in the config")
            mailboxes = [m for m in self.cfg.mailboxes if m.name != name]
            self._validate(mailboxes, self.cfg.agents)
            self.store.managed_write(delete={"mailboxes": [name]})
            self.load(force=True)

    def save_agent(
        self, data: dict[str, Any], existing: str | None
    ) -> tuple[AgentConfig, str | None]:
        """Create or update an agent's description, mailboxes and scopes.

        Returns the agent and, only when it was just created, its token.
        """
        with self._lock:
            self.load()
            old = next((a for a in self.cfg.agents if a.name == existing), None)
            if existing and old is None:
                raise ManageError(f"unknown agent {existing!r}")
            token = None
            fields = {
                "name": existing or data.get("name"),
                "description": str(data.get("description") or ""),
                "mailboxes": data.get("mailboxes") or [],
                "scopes": data.get("scopes") or [],
            }
            if old is not None:
                fields["token_sha256"] = (
                    old.token_sha256 or hashlib.sha256((old.token or "").encode()).hexdigest()
                )
            else:
                token = new_token()
                fields["token_sha256"] = hashlib.sha256(token.encode()).hexdigest()
            try:
                agent = AgentConfig.model_validate(fields)
            except ValidationError as e:
                raise ManageError(_first_error(e)) from e
            if old is None and any(a.name == agent.name for a in self.cfg.agents):
                raise ManageError(f"there is already an agent named {agent.name!r}")
            agents = [agent if a.name == agent.name else a for a in self.cfg.agents]
            if old is None:
                agents.append(agent)
            self._validate(self.cfg.mailboxes, agents)
            created = iso(now()) if token else self.token_dates().get(agent.name)
            self.store.managed_write(put={"agents": {agent.name: self._agent_row(agent, created)}})
            self.load(force=True)
            return agent, token

    def rotate_token(self, name: str) -> str:
        with self._lock:
            self.load()
            old = next((a for a in self.cfg.agents if a.name == name), None)
            if old is None:
                raise ManageError(f"unknown agent {name!r}")
            token = new_token()
            agent = old.model_copy(
                update={"token": None, "token_sha256": hashlib.sha256(token.encode()).hexdigest()}
            )
            self._validate(
                self.cfg.mailboxes, [agent if a.name == name else a for a in self.cfg.agents]
            )
            self.store.managed_write(put={"agents": {name: self._agent_row(agent, iso(now()))}})
            self.load(force=True)
            return token

    def delete_agent(self, name: str) -> None:
        with self._lock:
            self.load()
            if not any(a.name == name for a in self.cfg.agents):
                raise ManageError(f"unknown agent {name!r}")
            self.store.managed_write(delete={"agents": [name]})
            self.load(force=True)

    def export_yaml(self) -> str:
        """The current config as a file, passwords included, for backups or leaving the panel."""
        base = {k: v for k, v in self.base.items() if v is not None}
        if base.get("web"):
            base["web"] = {k: v for k, v in base["web"].items() if k != "setup_code"}
        data = {
            **base,
            "agents": [
                {
                    "name": a.name,
                    "description": a.description,
                    "token_sha256": a.token_sha256
                    or hashlib.sha256((a.token or "").encode()).hexdigest(),
                    "mailboxes": list(a.mailboxes),
                    "scopes": list(a.scopes),
                }
                for a in self.cfg.agents
            ],
            "mailboxes": [m.model_dump(exclude_none=True) for m in self.cfg.mailboxes],
        }
        head = (
            "# mailgrant config exported from the web app. It holds mailbox passwords:\n"
            "# keep it private. With web.manage on, the mailboxes and agents below are\n"
            "# ignored; turn it off (or start a fresh data_dir) to use them.\n"
        )
        return head + yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def uses(cfg: Config, mailbox: str) -> list[str]:
    """Agents that can reach a mailbox, by name or through "*"."""
    return [a.name for a in cfg.agents if ALL_MAILBOXES in a.mailboxes or mailbox in a.mailboxes]
