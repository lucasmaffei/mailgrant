"""SQLite state for the web app — and only for it.

Mail never lands here: messages stay on the IMAP servers. What this holds is
the web app's own bookkeeping (passkeys, sessions, invites, push devices,
notification choices), the new-mail watcher's cursors, and the audit history
the activity screen reads. Running MCP only never creates this file.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS credentials (
    id TEXT PRIMARY KEY,
    public_key BLOB NOT NULL,
    sign_count INTEGER NOT NULL DEFAULT 0,
    name TEXT NOT NULL,
    transports TEXT,
    created_at TEXT NOT NULL,
    last_used_at TEXT
);
CREATE TABLE IF NOT EXISTS invites (
    token_hash TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT,
    user_agent TEXT
);
CREATE TABLE IF NOT EXISTS challenges (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    challenge BLOB NOT NULL,
    invite_hash TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS push_subscriptions (
    endpoint TEXT PRIMARY KEY,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    user_agent TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prefs (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watch (
    mailbox TEXT PRIMARY KEY,
    uidvalidity INTEGER NOT NULL,
    uidnext INTEGER NOT NULL,
    unseen INTEGER NOT NULL DEFAULT 0,
    checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    agent TEXT NOT NULL,
    via TEXT NOT NULL,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL,
    mailbox TEXT,
    uid TEXT,
    message_id TEXT,
    in_reply_to TEXT,
    fields TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS managed_mailboxes (
    name TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS managed_agents (
    name TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_ts ON audit (ts);
CREATE INDEX IF NOT EXISTS audit_target ON audit (mailbox, uid);
CREATE INDEX IF NOT EXISTS audit_reply ON audit (in_reply_to);
"""

CHALLENGE_TTL = timedelta(minutes=5)
AUDIT_RETENTION = timedelta(days=180)


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Store:
    def __init__(self, data_dir: str) -> None:
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "mailgrant.db"
        # Every uvicorn worker builds a Store at the same moment on first start.
        # Switching to WAL needs an exclusive lock and doesn't wait on the busy
        # handler, so the losers retry instead of failing the worker.
        for attempt in range(50):
            try:
                with self._conn() as db:
                    db.execute("PRAGMA journal_mode=WAL")
                    db.executescript(SCHEMA)
                    cols = {r["name"] for r in db.execute("PRAGMA table_info(sessions)")}
                    if "confirmed_at" not in cols:  # added in 0.9
                        try:
                            db.execute("ALTER TABLE sessions ADD COLUMN confirmed_at TEXT")
                        except sqlite3.OperationalError as e:
                            # Another process starting at the same time got there first.
                            if "duplicate column" not in str(e):
                                raise
                break
            except sqlite3.OperationalError as e:
                if "locked" not in str(e) or attempt == 49:
                    raise
                time.sleep(0.1)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        # One short connection per operation keeps this safe across uvicorn
        # workers and the watcher thread; WAL (set once, stored in the file)
        # lets readers run during writes.
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=10000")
            yield db
            db.commit()
        finally:
            db.close()

    # ── invites ───────────────────────────────────────────────────────────

    def create_invite(self, ttl: timedelta) -> str:
        # Hex, not urlsafe: a link ending in "_" or "-" loses that last
        # character when a terminal or chat app turns it into a link.
        token = secrets.token_hex(16)
        with self._conn() as db:
            db.execute(
                "INSERT INTO invites (token_hash, created_at, expires_at) VALUES (?, ?, ?)",
                (digest(token), iso(now()), iso(now() + ttl)),
            )
        return token

    def invite_valid(self, token: str) -> bool:
        with self._conn() as db:
            row = db.execute(
                "SELECT expires_at, used_at FROM invites WHERE token_hash = ?", (digest(token),)
            ).fetchone()
        return bool(row) and row["used_at"] is None and row["expires_at"] > iso(now())

    def use_invite(self, token_hash: str) -> bool:
        with self._conn() as db:
            cur = db.execute(
                "UPDATE invites SET used_at = ? WHERE token_hash = ? AND used_at IS NULL "
                "AND expires_at > ?",
                (iso(now()), token_hash, iso(now())),
            )
            return cur.rowcount == 1

    # ── WebAuthn challenges ───────────────────────────────────────────────

    def put_challenge(self, kind: str, challenge: bytes, invite_hash: str | None = None) -> str:
        cid = secrets.token_urlsafe(18)
        with self._conn() as db:
            db.execute("DELETE FROM challenges WHERE created_at < ?", (iso(now() - CHALLENGE_TTL),))
            db.execute(
                "INSERT INTO challenges (id, kind, challenge, invite_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (cid, kind, challenge, invite_hash, iso(now())),
            )
        return cid

    def take_challenge(self, cid: str, kind: str) -> sqlite3.Row | None:
        """Single use: the row is deleted as it is read."""
        with self._conn() as db:
            row = db.execute(
                "SELECT * FROM challenges WHERE id = ? AND kind = ? AND created_at >= ?",
                (cid, kind, iso(now() - CHALLENGE_TTL)),
            ).fetchone()
            db.execute("DELETE FROM challenges WHERE id = ?", (cid,))
        return row

    # ── passkeys ──────────────────────────────────────────────────────────

    def add_credential(
        self, cred_id: str, public_key: bytes, sign_count: int, name: str, transports: list[str]
    ) -> None:
        with self._conn() as db:
            db.execute(
                "INSERT INTO credentials "
                "(id, public_key, sign_count, name, transports, created_at, last_used_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                # Registering signs this device in, so it counts as a use.
                (
                    cred_id,
                    public_key,
                    sign_count,
                    name,
                    json.dumps(transports),
                    iso(now()),
                    iso(now()),
                ),
            )

    def credentials(self) -> list[sqlite3.Row]:
        with self._conn() as db:
            return db.execute("SELECT * FROM credentials ORDER BY created_at").fetchall()

    def credential(self, cred_id: str) -> sqlite3.Row | None:
        with self._conn() as db:
            return db.execute("SELECT * FROM credentials WHERE id = ?", (cred_id,)).fetchone()

    def touch_credential(self, cred_id: str, sign_count: int) -> None:
        with self._conn() as db:
            db.execute(
                "UPDATE credentials SET sign_count = ?, last_used_at = ? WHERE id = ?",
                (sign_count, iso(now()), cred_id),
            )

    def delete_credential(self, cred_id: str) -> bool:
        with self._conn() as db:
            return db.execute("DELETE FROM credentials WHERE id = ?", (cred_id,)).rowcount == 1

    # ── sessions ──────────────────────────────────────────────────────────

    def create_session(self, days: int, user_agent: str | None) -> str:
        token = secrets.token_urlsafe(32)
        with self._conn() as db:
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (iso(now()),))
            db.execute(
                "INSERT INTO sessions "
                "(token_hash, created_at, expires_at, last_seen_at, user_agent) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    digest(token),
                    iso(now()),
                    iso(now() + timedelta(days=days)),
                    iso(now()),
                    (user_agent or "")[:200],
                ),
            )
        return token

    def session_valid(self, token: str) -> bool:
        h = digest(token)
        with self._conn() as db:
            row = db.execute(
                "SELECT expires_at FROM sessions WHERE token_hash = ?", (h,)
            ).fetchone()
            if not row or row["expires_at"] <= iso(now()):
                return False
            db.execute("UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?", (iso(now()), h))
        return True

    def confirm_session(self, token: str) -> None:
        """Record a fresh passkey check on this session (for sensitive changes)."""
        with self._conn() as db:
            db.execute(
                "UPDATE sessions SET confirmed_at = ? WHERE token_hash = ?",
                (iso(now()), digest(token)),
            )

    def session_confirmed(self, token: str, within: timedelta) -> bool:
        with self._conn() as db:
            row = db.execute(
                "SELECT confirmed_at FROM sessions WHERE token_hash = ?", (digest(token),)
            ).fetchone()
        return bool(row and row["confirmed_at"] and row["confirmed_at"] > iso(now() - within))

    def end_session(self, token: str) -> None:
        with self._conn() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (digest(token),))

    def end_all_sessions(self) -> None:
        with self._conn() as db:
            db.execute("DELETE FROM sessions")

    # ── push ──────────────────────────────────────────────────────────────

    def add_push(self, endpoint: str, p256dh: str, auth: str, user_agent: str | None) -> None:
        with self._conn() as db:
            db.execute(
                "INSERT OR REPLACE INTO push_subscriptions "
                "(endpoint, p256dh, auth, user_agent, created_at) VALUES (?, ?, ?, ?, ?)",
                (endpoint, p256dh, auth, (user_agent or "")[:200], iso(now())),
            )

    def remove_push(self, endpoint: str) -> None:
        with self._conn() as db:
            db.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))

    def push_subscriptions(self) -> list[sqlite3.Row]:
        with self._conn() as db:
            return db.execute("SELECT * FROM push_subscriptions").fetchall()

    # ── prefs ─────────────────────────────────────────────────────────────

    def get_pref(self, key: str, default: Any = None) -> Any:
        with self._conn() as db:
            row = db.execute("SELECT value FROM prefs WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_pref(self, key: str, value: Any) -> None:
        with self._conn() as db:
            db.execute(
                "INSERT OR REPLACE INTO prefs (key, value) VALUES (?, ?)", (key, json.dumps(value))
            )

    # ── watcher ───────────────────────────────────────────────────────────

    def watch_state(self, mailbox: str) -> sqlite3.Row | None:
        with self._conn() as db:
            return db.execute("SELECT * FROM watch WHERE mailbox = ?", (mailbox,)).fetchone()

    def set_watch_state(self, mailbox: str, uidvalidity: int, uidnext: int, unseen: int) -> None:
        with self._conn() as db:
            db.execute(
                "INSERT OR REPLACE INTO watch (mailbox, uidvalidity, uidnext, unseen, checked_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (mailbox, uidvalidity, uidnext, unseen, iso(now())),
            )

    def unseen_total(self, mailboxes: list[str]) -> int:
        if not mailboxes:
            return 0
        marks = ",".join("?" * len(mailboxes))
        with self._conn() as db:
            row = db.execute(
                f"SELECT COALESCE(SUM(unseen), 0) AS n FROM watch WHERE mailbox IN ({marks})",
                mailboxes,
            ).fetchone()
        return int(row["n"])

    # ── audit history ─────────────────────────────────────────────────────

    def add_audit(self, entry: dict[str, Any], via: str) -> None:
        known = {"ts", "agent", "action", "outcome", "mailbox", "uid", "message_id", "in_reply_to"}
        rest = {k: v for k, v in entry.items() if k not in known}
        with self._conn() as db:
            db.execute(
                "INSERT INTO audit (ts, agent, via, action, outcome, mailbox, uid, message_id, "
                "in_reply_to, fields) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry["ts"],
                    entry["agent"],
                    via,
                    entry["action"],
                    entry["outcome"],
                    entry.get("mailbox"),
                    entry.get("uid"),
                    entry.get("message_id"),
                    entry.get("in_reply_to"),
                    json.dumps(rest, ensure_ascii=False, default=str),
                ),
            )
            if secrets.randbelow(200) == 0:  # trim now and then, not on every write
                db.execute("DELETE FROM audit WHERE ts < ?", (iso(now() - AUDIT_RETENTION),))

    def agent_activity(self, kind: str | None, limit: int) -> list[sqlite3.Row]:
        # Listing a mailbox says nothing a person needs to see; it would bury
        # the reads, sends and refusals that matter.
        where = "via = 'agent' AND action NOT IN ('inbox')"
        if kind == "sent":
            where += " AND action = 'send' AND outcome = 'ok'"
        elif kind == "denied":
            where += " AND outcome = 'denied'"
        with self._conn() as db:
            return db.execute(
                f"SELECT * FROM audit WHERE {where} ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()

    def agent_marks(self, since: datetime) -> list[sqlite3.Row]:
        """Successful agent reads and replies, for the 'hermes leu' marks in lists."""
        with self._conn() as db:
            return db.execute(
                "SELECT agent, action, mailbox, uid, in_reply_to, ts FROM audit "
                "WHERE via = 'agent' AND outcome = 'ok' AND action IN ('get_message', 'send') "
                "AND ts >= ? ORDER BY id",
                (iso(since),),
            ).fetchall()

    def senders(self, message_ids: list[str]) -> dict[str, tuple[str, str]]:
        """message_id -> (who sent it, "agent" or "person"), for the Sent view."""
        ids = [m for m in message_ids if m]
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        with self._conn() as db:
            rows = db.execute(
                f"SELECT message_id, agent, via FROM audit WHERE action = 'send' "
                f"AND outcome = 'ok' AND message_id IN ({marks})",
                ids,
            ).fetchall()
        return {r["message_id"]: (r["agent"], r["via"]) for r in rows}

    # ── mailboxes and agents managed from the web app ─────────────────────

    def managed_rows(self, kind: str) -> list[sqlite3.Row]:
        table = {"mailboxes": "managed_mailboxes", "agents": "managed_agents"}[kind]
        with self._conn() as db:
            return db.execute(f"SELECT name, data FROM {table} ORDER BY rowid").fetchall()

    def managed_write(
        self,
        put: dict[str, dict[str, dict[str, Any]]] | None = None,
        delete: dict[str, list[str]] | None = None,
    ) -> int:
        """Apply upserts and deletes in one transaction; returns the new version."""
        tables = {"mailboxes": "managed_mailboxes", "agents": "managed_agents"}
        with self._conn() as db:
            for kind, rows in (put or {}).items():
                for name, data in rows.items():
                    db.execute(
                        f"INSERT INTO {tables[kind]} (name, data, updated_at) VALUES (?, ?, ?) "
                        "ON CONFLICT(name) DO UPDATE SET data = excluded.data, "
                        "updated_at = excluded.updated_at",
                        (name, json.dumps(data), iso(now())),
                    )
            for kind, names in (delete or {}).items():
                for name in names:
                    db.execute(f"DELETE FROM {tables[kind]} WHERE name = ?", (name,))
            row = db.execute("SELECT value FROM prefs WHERE key = 'config_version'").fetchone()
            version = (json.loads(row["value"]) if row else 0) + 1
            db.execute(
                "INSERT OR REPLACE INTO prefs (key, value) VALUES ('config_version', ?)",
                (json.dumps(version),),
            )
        return version

    def config_version(self) -> int:
        return int(self.get_pref("config_version", 0))
