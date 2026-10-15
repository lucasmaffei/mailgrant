"""YAML config loader.

Single file, validated via pydantic. Each mailbox can have any subset of
{imap, smtp} — at least one is required. `name` must be unique and
URL-safe (it becomes a path segment in the HTTP API).

`agents` grant each bearer token a set of mailboxes and scopes. String values
may reference environment variables as `${NAME}`, so secrets can live in the
deployment platform instead of the file.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator

DEFAULT_CONFIG_PATH = "/etc/mailgrant/config.yaml"
_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_ENV_REF_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

ALL_MAILBOXES = "*"

TlsMode = Literal["ssl", "starttls", "none"]
Scope = Literal["read", "mark", "delete", "send"]
ALL_SCOPES: tuple[str, ...] = ("read", "mark", "delete", "send")


class ImapConfig(BaseModel):
    host: str
    port: int = 993
    tls: TlsMode = "ssl"
    username: str
    password: str
    default_folder: str = "INBOX"
    # Where delete moves messages. Unset: the folder flagged \\Trash, then
    # common names (Trash, Deleted Items, Lixeira).
    trash_folder: str | None = None


class SmtpConfig(BaseModel):
    host: str
    port: int = 587
    tls: TlsMode = "starttls"
    username: str
    password: str
    from_address: str
    # Extra addresses a caller may put in From:. Anything else is refused, so a
    # token scoped to one mailbox can't impersonate another address.
    allowed_from: list[str] = Field(default_factory=list)
    # IMAP folder that receives a copy of every message sent through this
    # mailbox (needs `imap`). Plain SMTP never stores one, so without it the
    # humans sharing the mailbox can't see what an agent wrote.
    save_copy_to: str | None = None


class MailboxConfig(BaseModel):
    name: str
    description: str = ""
    imap: ImapConfig | None = None
    smtp: SmtpConfig | None = None

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError(f"mailbox name {v!r} invalid: must match [a-zA-Z0-9_-]+")
        return v

    @model_validator(mode="after")
    def _has_at_least_one_protocol(self) -> "MailboxConfig":
        if self.imap is None and self.smtp is None:
            raise ValueError(
                f"mailbox {self.name!r} declares no protocols — " "set at least one of imap / smtp"
            )
        return self


class AgentConfig(BaseModel):
    """One bearer token and what it may touch.

    Exactly one of `token` (plaintext, usually `${ENV_VAR}`) or `token_sha256`
    (hex digest, safe to keep in the file) identifies the agent.
    """

    name: str
    description: str = ""
    token: str | None = None
    token_sha256: str | None = None
    mailboxes: list[str] = Field(..., min_length=1)
    scopes: list[Scope] = Field(..., min_length=1)

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError(f"agent name {v!r} invalid: must match [a-zA-Z0-9_-]+")
        return v

    @field_validator("token_sha256")
    @classmethod
    def _check_digest(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower().removeprefix("sha256:")
        if not _SHA256_RE.match(v):
            raise ValueError("token_sha256 must be 64 hex characters")
        return v

    @model_validator(mode="after")
    def _one_credential(self) -> "AgentConfig":
        if (self.token is None) == (self.token_sha256 is None):
            raise ValueError(f"agent {self.name!r}: set exactly one of token / token_sha256")
        if self.token is not None and not self.token.strip():
            raise ValueError(f"agent {self.name!r}: token must not be empty")
        return self


class WebUserConfig(BaseModel):
    """The person who signs in to the web app, granted like an agent."""

    name: str = "owner"
    mailboxes: list[str] = Field(default_factory=lambda: [ALL_MAILBOXES], min_length=1)
    scopes: list[Scope] = Field(
        default_factory=lambda: list(ALL_SCOPES), min_length=1  # type: ignore[arg-type]
    )

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError(f"web user name {v!r} invalid: must match [a-zA-Z0-9_-]+")
        return v


class WebConfig(BaseModel):
    """Optional web app (inbox, agent activity, push). Leave the section out to run MCP only."""

    enabled: bool = True
    # Public URL the app is served from. Passkeys are bound to its host, and
    # requests from any other origin are refused.
    origin: str
    # SQLite lives here: passkeys, sessions, push subscriptions, audit history.
    data_dir: str = "/data"
    session_days: int = Field(30, ge=1, le=365)
    # How often each mailbox is checked for new mail (one STATUS per mailbox).
    poll_seconds: int = Field(60, ge=15, le=3600)
    # Contact the push services may use (RFC 8292); defaults to the origin.
    push_contact: str | None = None
    # Lets the first passkey be created by typing this code on the sign-in
    # screen, instead of opening a `mailgrant invite` link. Only works while no
    # passkey exists. Falls back to the MAILGRANT_SETUP_CODE environment variable.
    setup_code: str | None = None
    # Manage mailboxes and agents from the web app. They then live in the
    # database (imported from this file the first time) and the `mailboxes`
    # and `agents` sections here are ignored.
    manage: bool = False
    user: WebUserConfig = Field(default_factory=WebUserConfig)

    @model_validator(mode="after")
    def _setup_code_from_env(self) -> WebConfig:
        if self.setup_code is None:
            self.setup_code = os.environ.get("MAILGRANT_SETUP_CODE") or None
        if self.setup_code is not None:
            self.setup_code = self.setup_code.strip()
            if len(self.setup_code) < 12:
                raise ValueError(
                    "web.setup_code (or MAILGRANT_SETUP_CODE) must be at least 12 characters"
                )
        return self

    @field_validator("origin")
    @classmethod
    def _check_origin(cls, v: str) -> str:
        v = v.rstrip("/")
        local = v.startswith(("http://localhost", "http://127.0.0.1"))
        if not (v.startswith("https://") or local) or v.count("/") != 2:
            raise ValueError(
                "web.origin must be https://host[:port] (http only for localhost): "
                "passkeys and push need a secure origin"
            )
        return v


class AuthConfig(BaseModel):
    """Legacy bearer tokens with full access. Prefer `agents` for anything new."""

    tokens: list[str] = Field(default_factory=list)

    @field_validator("tokens")
    @classmethod
    def _no_empty_tokens(cls, v: list[str]) -> list[str]:
        for t in v:
            if not t or not t.strip():
                raise ValueError("auth.tokens must not contain empty strings")
        return v


class Config(BaseModel):
    log_level: str = "INFO"
    # One JSON line per operation on the `mailgrant.audit` logger: which agent
    # did what, on which mailbox, and whether it was allowed.
    audit_log: bool = True
    auth: AuthConfig = Field(default_factory=AuthConfig)
    agents: list[AgentConfig] = Field(default_factory=list)
    web: WebConfig | None = None
    mailboxes: list[MailboxConfig] = Field(default_factory=list)
    # Set by the web app when it manages mailboxes and agents: brings this
    # object up to date with changes saved by any worker.
    _refresh: Any = PrivateAttr(default=None)

    def refresh(self) -> None:
        if self._refresh is not None:
            self._refresh()

    @model_validator(mode="after")
    def _unique_names(self) -> "Config":
        seen: set[str] = set()
        for m in self.mailboxes:
            if m.name in seen:
                raise ValueError(f"duplicate mailbox name: {m.name!r}")
            seen.add(m.name)
        return self

    @model_validator(mode="after")
    def _check_agents(self) -> "Config":
        names: set[str] = set()
        for a in self.agents:
            if a.name in names:
                raise ValueError(f"duplicate agent name: {a.name!r}")
            names.add(a.name)
            for ref in a.mailboxes:
                # A typo here would silently grant nothing; fail loudly instead.
                if ref != ALL_MAILBOXES and self.find(ref) is None:
                    raise ValueError(f"agent {a.name!r} references unknown mailbox {ref!r}")
        # Compare digests so a plaintext token and another agent's token_sha256
        # can't collide either: the first match would silently win.
        plain = [a.token for a in self.agents if a.token is not None] + list(self.auth.tokens)
        digests = [hashlib.sha256(t.encode("utf-8")).hexdigest() for t in plain]
        digests += [a.token_sha256 for a in self.agents if a.token_sha256 is not None]
        if len(digests) != len(set(digests)):
            raise ValueError("the same token is configured more than once")
        if self.web is not None:
            if self.web.user.name in names:
                raise ValueError(f"web user {self.web.user.name!r} has the same name as an agent")
            for ref in self.web.user.mailboxes:
                if ref != ALL_MAILBOXES and self.find(ref) is None:
                    raise ValueError(f"web user references unknown mailbox {ref!r}")
        for m in self.mailboxes:
            if m.smtp is not None and m.smtp.save_copy_to and m.imap is None:
                raise ValueError(f"mailbox {m.name!r}: smtp.save_copy_to needs imap configured")
        return self

    @property
    def web_enabled(self) -> bool:
        return self.web is not None and self.web.enabled

    @property
    def managed(self) -> bool:
        return self.web_enabled and self.web is not None and self.web.manage

    def get(self, name: str) -> MailboxConfig | None:
        for m in self.mailboxes:
            if m.name == name:
                return m
        return None

    def find(self, ident: str) -> MailboxConfig | None:
        """Look up a mailbox by name or by its IMAP/SMTP username (address)."""
        for m in self.mailboxes:
            if m.name == ident:
                return m
            if m.imap is not None and m.imap.username == ident:
                return m
            if m.smtp is not None and m.smtp.username == ident:
                return m
        return None


class ConfigError(Exception):
    """Raised when config can't be loaded or is invalid."""


def load_config(path: str | None = None) -> Config:
    # The whole YAML may come from the environment, which is how platforms hand
    # over a secret without mounting a file. MAILGRANT_CONFIG_B64 exists because
    # some of them (Coolify among them) write variables to a dotenv file, where
    # a multi-line value breaks the parser. An explicit path still wins, so
    # `mailgrant check --config` reads what it is told.
    inline: str | None = None
    source = ""
    if not path and os.environ.get("MAILGRANT_CONFIG_B64"):
        source = "MAILGRANT_CONFIG_B64"
        try:
            inline = base64.b64decode(os.environ[source], validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as e:
            raise ConfigError(f"{source} is not valid base64-encoded UTF-8: {e}") from e
    elif not path and os.environ.get("MAILGRANT_CONFIG_YAML"):
        source, inline = "MAILGRANT_CONFIG_YAML", os.environ["MAILGRANT_CONFIG_YAML"]
    cfg_path = source or path or os.environ.get("MAILGRANT_CONFIG") or DEFAULT_CONFIG_PATH
    if inline is None:
        p = Path(cfg_path)
        if not p.is_file():
            raise ConfigError(f"config not found: {cfg_path}")
        inline = p.read_text(encoding="utf-8")
    try:
        raw = yaml.safe_load(inline)
    except yaml.YAMLError as e:
        raise ConfigError(f"config {cfg_path} is not valid YAML: {e}") from e
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(f"config {cfg_path} must be a YAML mapping")
    raw = _expand_env(raw, cfg_path)
    try:
        return Config.model_validate(raw)
    except Exception as e:
        raise ConfigError(f"config {cfg_path} invalid: {e}") from e


def _expand_env(value: Any, cfg_path: str) -> Any:
    """Replace `${NAME}` in every string with the environment variable's value.

    A missing variable is an error rather than an empty string: an empty
    password or token would fail later in a far less obvious way.
    """
    if isinstance(value, dict):
        return {k: _expand_env(v, cfg_path) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v, cfg_path) for v in value]
    if not isinstance(value, str):
        return value

    def sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in os.environ:
            raise ConfigError(
                f"config {cfg_path} references unset environment variable ${{{name}}}"
            )
        return os.environ[name]

    return _ENV_REF_RE.sub(sub, value)
