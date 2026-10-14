"""Who is calling and what they may touch.

Every authenticated request carries a `Principal`. The HTTP API and the MCP
server both ask it the same two questions — may this caller see that mailbox,
and does it hold that scope — so the rules live here and nowhere else.

A mailbox outside the caller's grant answers exactly like a mailbox that does
not exist. Telling the two apart would let a narrow token map out every
address the instance serves.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from email.utils import parseaddr

from .config import ALL_MAILBOXES, ALL_SCOPES, Config, MailboxConfig, SmtpConfig


class NotFound(Exception):
    """Mailbox unknown or not granted to the caller (deliberately indistinguishable)."""


class Forbidden(Exception):
    """Mailbox granted, but the operation needs a scope the caller lacks."""


@dataclass(frozen=True)
class Principal:
    name: str
    scopes: frozenset[str]
    # Mailbox names this principal may use; None means every mailbox, including
    # ones added to the config later.
    mailboxes: frozenset[str] | None

    def can_see(self, mb: MailboxConfig) -> bool:
        return self.mailboxes is None or mb.name in self.mailboxes

    def has(self, scope: str) -> bool:
        return scope in self.scopes

    def require(self, scope: str) -> None:
        if scope not in self.scopes:
            raise Forbidden(f"agent {self.name!r} lacks the {scope!r} scope")

    def visible(self, cfg: Config) -> list[MailboxConfig]:
        return [m for m in cfg.mailboxes if self.can_see(m)]


def _principal_for_agent(cfg: Config, index: int) -> Principal:
    agent = cfg.agents[index]
    if ALL_MAILBOXES in agent.mailboxes:
        allowed: frozenset[str] | None = None
    else:
        names = set()
        for ref in agent.mailboxes:
            mb = cfg.find(ref)
            if mb is not None:
                names.add(mb.name)
        allowed = frozenset(names)
    return Principal(name=agent.name, scopes=frozenset(agent.scopes), mailboxes=allowed)


def authenticate(cfg: Config, presented: str | None) -> Principal | None:
    """Map a bearer token to its principal, or None when it matches nothing.

    Every candidate is compared, match or not, so response time doesn't reveal
    which entry (if any) a guessed token came close to.
    """
    if not presented:
        return None
    digest = hashlib.sha256(presented.encode("utf-8")).hexdigest()
    found: Principal | None = None

    for i, tok in enumerate(cfg.auth.tokens):
        if hmac.compare_digest(tok.encode("utf-8"), presented.encode("utf-8")) and found is None:
            found = Principal(
                name="legacy-token" if len(cfg.auth.tokens) == 1 else f"legacy-token-{i + 1}",
                scopes=frozenset(ALL_SCOPES),
                mailboxes=None,
            )
    for i, agent in enumerate(cfg.agents):
        if agent.token is not None:
            hit = hmac.compare_digest(agent.token.encode("utf-8"), presented.encode("utf-8"))
        else:
            hit = hmac.compare_digest(agent.token_sha256 or "", digest)
        if hit and found is None:
            found = _principal_for_agent(cfg, i)
    return found


def resolve(cfg: Config, principal: Principal, ident: str) -> MailboxConfig:
    """Find a mailbox by name or address, as long as the principal may see it."""
    if not ident:
        raise ValueError("`mailbox` is required")
    mb = cfg.find(ident)
    if mb is None or not principal.can_see(mb):
        raise NotFound(f"unknown mailbox: {ident!r}")
    return mb


def select_imap(cfg: Config, principal: Principal, filter_csv: str | None) -> list[MailboxConfig]:
    """Targets for the unified inbox: the caller's IMAP mailboxes, optionally filtered.

    Filter entries outside the grant are ignored like unknown ones, and an
    empty result is an error so a typo doesn't look like an empty inbox.
    """
    pool = [m for m in principal.visible(cfg) if m.imap is not None]
    if not filter_csv:
        return pool
    wanted = {s.strip() for s in filter_csv.split(",") if s.strip()}
    out = [m for m in pool if m.name in wanted or (m.imap and m.imap.username in wanted)]
    if not out:
        raise NotFound(f"no IMAP-enabled mailboxes matched filter: {filter_csv!r}")
    return out


def check_sender(smtp: SmtpConfig, from_address: str | None) -> None:
    """Refuse a From: that isn't the mailbox's own address or an allowed alias."""
    if not from_address:
        return
    wanted = parseaddr(from_address)[1].lower()
    allowed = {parseaddr(smtp.from_address)[1].lower(), smtp.username.lower()}
    allowed.update(parseaddr(a)[1].lower() for a in smtp.allowed_from)
    if not wanted or wanted not in allowed:
        raise Forbidden(
            f"from_address {from_address!r} is not allowed for this mailbox; "
            "add it to smtp.allowed_from"
        )
