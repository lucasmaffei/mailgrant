"""Audit trail: one JSON line per mail operation on the `mailgrant.audit` logger.

Kept to metadata — agent, action, mailbox, UID, recipients, outcome. Message
bodies and subjects never go here: the log usually ends up somewhere with
looser access than the mailboxes themselves.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("mailgrant.audit")

_enabled = True


def configure(enabled: bool) -> None:
    global _enabled
    _enabled = enabled


def record(agent: str, action: str, outcome: str = "ok", **fields: Any) -> None:
    if not _enabled:
        return
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent": agent,
        "action": action,
        "outcome": outcome,
    }
    entry.update({k: v for k, v in fields.items() if v is not None})
    log.info(json.dumps(entry, ensure_ascii=False, default=str))
