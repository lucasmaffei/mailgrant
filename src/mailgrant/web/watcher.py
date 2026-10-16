"""New-mail watcher: polls each mailbox and pushes what arrived.

A STATUS per mailbox per round (UIDNEXT tells whether anything arrived) is
cheap enough to poll every minute, and simpler to keep healthy than one IDLE
connection per mailbox. The first round only records where each mailbox is,
so starting the server never replays old mail as notifications.

Only one process watches: with several uvicorn workers, the one holding the
lock file does it and the rest skip.
"""

from __future__ import annotations

import fcntl
import logging
import threading
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from ..config import Config
from ..grants import web_principal
from ..imap_client import ImapError, headers_since, mailbox_status
from . import i18n
from .push import Pusher
from .store import Store

log = logging.getLogger("mailgrant.web.watcher")

MAX_PUSHES_PER_MAILBOX = 5


def sender_name(raw: str, lang: str = "en") -> str:
    name, addr = parseaddr(raw or "")
    return name or addr or i18n.text(lang, "new_mail")


class Watcher:
    def __init__(self, cfg: Config, store: Store, pusher: Pusher) -> None:
        assert cfg.web is not None
        self.cfg = cfg
        self.store = store
        self.pusher = pusher
        self.interval = cfg.web.poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock_file: Any = None

    def start(self) -> bool:
        lock_path = Path(self.store.dir) / "watcher.lock"
        self._lock_file = open(lock_path, "w")
        try:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lock_file.close()
            self._lock_file = None
            return False  # another worker watches
        self._thread = threading.Thread(target=self._run, name="mailgrant-watcher", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self._lock_file is not None:
            self._lock_file.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception:  # noqa: BLE001 - keep watching whatever happened
                log.exception("watcher round failed")
            self._stop.wait(self.interval)

    def mailboxes(self) -> list[Any]:
        who = web_principal(self.cfg)
        return [m for m in who.visible(self.cfg) if m.imap is not None]

    def check_once(self) -> list[dict[str, Any]]:
        """One round over every mailbox; returns the notifications it sent."""
        self.cfg.refresh()
        notify = self.store.get_pref("notify", {})
        fresh: list[tuple[Any, dict[str, Any]]] = []
        for mb in self.mailboxes():
            try:
                st = mailbox_status(mb.imap)
                prev = self.store.watch_state(mb.name)
                if (
                    prev is not None
                    and prev["uidvalidity"] == st["uidvalidity"]
                    and st["uidnext"] > prev["uidnext"]
                    and notify.get(mb.name, True)
                ):
                    new = headers_since(mb.imap, prev["uidnext"], limit=MAX_PUSHES_PER_MAILBOX)
                    fresh += [(mb, h) for h in new if "\\Seen" not in h.get("flags", [])]
                self.store.set_watch_state(mb.name, st["uidvalidity"], st["uidnext"], st["unseen"])
            except (ImapError, OSError) as e:
                log.warning("watcher: %s: %s", mb.name, e)

        if not fresh:
            return []
        badge = self.store.unseen_total([m.name for m in self.mailboxes()])
        sent = []
        lang = i18n.language(self.store)
        for mb, h in reversed(fresh):  # oldest first, so the newest ends on top
            payload = {
                "title": sender_name(h.get("from", ""), lang),
                "body": h.get("subject") or i18n.text(lang, "no_subject"),
                "tag": f"{mb.name}:{h.get('uid')}",
                "url": f"/app/#/m/{mb.name}/{h.get('uid')}",
                "mailbox": mb.imap.username,
                "badge": badge,
            }
            self.pusher.send_all(payload)
            sent.append(payload)
        return sent
