"""IMAP operations: list folders, list/fetch/delete messages.

Connections are short-lived — opened per request and closed in a finally
block. Long-lived pooling would be nice but isn't worth the lifecycle
complexity for a control-plane API. UIDs (not sequence numbers) are used
everywhere so subsequent operations stay stable across mailbox mutations.
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Any, Iterator

import html2text

from .config import ImapConfig, MailboxConfig

log = logging.getLogger(__name__)


def _html_to_reader(html: str) -> str:
    """Strip HTML chrome and return readable plain-text/markdown.

    Designed for email bodies: drops style/script, flattens tables, keeps
    links inline, ignores images. Output is wrapped at a sane width so
    long marketing-email lines don't blow out terminals.
    """
    h = html2text.HTML2Text()
    h.body_width = 0
    h.ignore_images = True
    h.ignore_emphasis = False
    h.single_line_break = False
    h.skip_internal_links = True
    h.unicode_snob = True
    return h.handle(html).strip()


class ImapError(Exception):
    """Raised when an IMAP operation fails."""


# IMAP command lines are CRLF-delimited and its atoms/quoted-strings cannot
# contain CR, LF or NUL. Python's imaplib passes caller-supplied arguments to
# the server verbatim (no sanitization), so a CR/LF smuggled into a
# folder/uid/search value would terminate the current command and inject an
# additional, attacker-chosen IMAP command onto the same authenticated
# connection (issue #1: command injection, incl. STORE+EXPUNGE through a
# read-only GET route). Reject those bytes at the boundary, before any value
# reaches imaplib.
_FORBIDDEN_CHARS = ("\r", "\n", "\x00")

# Every operation here targets exactly one message, so a UID is digits only.
# Sets and ranges (`1:*`, `3,4`) are refused: with them a single delete call
# would wipe a whole folder. Digits-only is also injection-proof by construction.
_UID_RE = re.compile(r"^[1-9][0-9]*$")

# LIST response: (\HasNoChildren \Trash) "/" "Deleted Items"
_LIST_RE = re.compile(r'^\((?P<flags>[^)]*)\) (?P<delim>"(?:[^"\\]|\\.)*"|NIL) (?P<name>.+)$')


def _reject_control_chars(value: str, field: str) -> None:
    if any(ch in value for ch in _FORBIDDEN_CHARS):
        raise ImapError(f"invalid {field}: control characters are not allowed")


def _validate_uid(uid: str) -> None:
    if not _UID_RE.match(uid):
        raise ImapError(f"invalid uid: {uid!r}")


@contextmanager
def _connect(cfg: ImapConfig) -> Iterator[imaplib.IMAP4]:
    if cfg.tls == "ssl":
        conn: imaplib.IMAP4 = imaplib.IMAP4_SSL(cfg.host, cfg.port)
    else:
        conn = imaplib.IMAP4(cfg.host, cfg.port)
    try:
        if cfg.tls == "starttls":
            conn.starttls()
        try:
            conn.login(cfg.username, cfg.password)
        except imaplib.IMAP4.error as e:
            raise ImapError(f"login failed: {e}") from e
        yield conn
    finally:
        try:
            conn.logout()
        except (imaplib.IMAP4.error, OSError) as error:
            log.warning("IMAP logout failed", extra={"error_type": type(error).__name__})
            try:
                conn.shutdown()
            except OSError as close_error:
                log.warning(
                    "IMAP socket close failed", extra={"error_type": type(close_error).__name__}
                )


def _decode(s: Any) -> str:
    if s is None:
        return ""
    if isinstance(s, bytes):
        try:
            s = s.decode("utf-8")
        except UnicodeDecodeError:
            s = s.decode("latin-1", errors="replace")
    try:
        return str(make_header(decode_header(str(s))))
    except Exception:
        return str(s)


def _select(conn: imaplib.IMAP4, folder: str, readonly: bool = False) -> None:
    _reject_control_chars(folder, "folder")
    # Send the name as a properly-escaped IMAP quoted string so an embedded
    # `"` or `\` cannot break out of the quoting either.
    escaped = folder.replace("\\", "\\\\").replace('"', '\\"')
    typ, _ = conn.select(f'"{escaped}"', readonly=readonly)
    if typ != "OK":
        raise ImapError(f"could not select folder {folder!r}")


def _parse_list(data: list[Any] | None) -> list[tuple[str, set[str]]]:
    """(name, flags) per LIST line. Names may contain spaces ("Caixa de entrada")."""
    out: list[tuple[str, set[str]]] = []
    for raw in data or []:
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        m = _LIST_RE.match(line.strip())
        if not m:
            continue
        name = m.group("name").strip()
        if len(name) >= 2 and name[0] == '"' and name[-1] == '"':
            name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        if name:
            out.append((name, {f.lower() for f in m.group("flags").split()}))
    return out


def _list(conn: imaplib.IMAP4) -> list[tuple[str, set[str]]]:
    typ, data = conn.list()
    if typ != "OK":
        raise ImapError("LIST failed")
    return _parse_list(data)


def list_folders(cfg: ImapConfig) -> list[str]:
    with _connect(cfg) as conn:
        return [name for name, _ in _list(conn)]


def _quote(folder: str) -> str:
    _reject_control_chars(folder, "folder")
    return '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _find_trash(conn: imaplib.IMAP4, cfg: ImapConfig) -> str | None:
    """The configured trash folder, else the one flagged \\Trash, else one named Trash."""
    folders = _list(conn)
    names = {name for name, _ in folders}
    if cfg.trash_folder:
        return cfg.trash_folder if cfg.trash_folder in names else None
    for name, flags in folders:
        if "\\trash" in flags:
            return name
    for candidate in ("Trash", "INBOX.Trash", "Deleted Items", "Lixeira"):
        if candidate in names:
            return candidate
    return None


def _has_capability(conn: imaplib.IMAP4, cap: str) -> bool:
    # imaplib keeps the pre-login CAPABILITY list, and servers such as Dovecot
    # only advertise MOVE/UIDPLUS after authentication — so ask again.
    caps: set[str] | None = getattr(conn, "_mailgrant_caps", None)
    if caps is None:
        typ, data = conn.capability()
        caps = set()
        if typ == "OK":
            for raw in data or []:
                text = raw.decode("ascii", "replace") if isinstance(raw, bytes) else str(raw)
                caps.update(c.upper() for c in text.split())
        setattr(conn, "_mailgrant_caps", caps)
    return cap.upper() in caps


def _expunge_uid(conn: imaplib.IMAP4, uid: str) -> None:
    """Remove exactly one \\Deleted message.

    A bare EXPUNGE would also remove every other message flagged \\Deleted in
    the folder — including ones a human marked in their own mail client.
    """
    if not _has_capability(conn, "UIDPLUS"):
        raise ImapError(
            "server lacks UIDPLUS; refusing a bare EXPUNGE that could remove other messages"
        )
    typ, _ = conn.uid("EXPUNGE", uid)
    if typ != "OK":
        raise ImapError(f"UID EXPUNGE failed for UID {uid}")


def build_search_criteria(
    text: str | None = None,
    from_: str | None = None,
    to: str | None = None,
    subject: str | None = None,
    body: str | None = None,
    since: str | None = None,
    before: str | None = None,
    unseen: bool | None = None,
    seen: bool | None = None,
    flagged: bool | None = None,
    answered: bool | None = None,
    larger_than: int | None = None,
    smaller_than: int | None = None,
) -> list[str | bytes]:
    """Translate a structured search request into an IMAP SEARCH criteria list.

    Returns a list of tokens ready to splat into `conn.uid("SEARCH", *tokens)`.
    Strings with non-ASCII content are encoded as IMAP `CHARSET UTF-8 ...`
    literal byte tokens — most modern servers accept this.
    """
    crit: list[str | bytes] = []

    def _q(value: str) -> str | bytes:
        _reject_control_chars(value, "search term")
        # IMAP atoms must be quoted strings or literals. imaplib quotes
        # automatically when the value is a plain `str`, but trips on
        # non-ASCII. For non-ASCII we hand back a literal byte token.
        if any(ord(c) > 127 for c in value):
            return value.encode("utf-8")
        # Escape backslash + quote for inside a quoted string.
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    has_nonascii = False

    def _add_text(key: str, value: str) -> None:
        nonlocal has_nonascii
        if any(ord(c) > 127 for c in value):
            has_nonascii = True
        crit.append(key)
        crit.append(_q(value))

    if from_:
        _add_text("FROM", from_)
    if to:
        _add_text("TO", to)
    if subject:
        _add_text("SUBJECT", subject)
    if body:
        _add_text("BODY", body)
    if text:
        _add_text("TEXT", text)
    if since:
        _reject_control_chars(since, "since")
        crit.extend(["SINCE", since])
    if before:
        _reject_control_chars(before, "before")
        crit.extend(["BEFORE", before])
    if unseen:
        crit.append("UNSEEN")
    if seen:
        crit.append("SEEN")
    if flagged:
        crit.append("FLAGGED")
    if answered:
        crit.append("ANSWERED")
    if larger_than is not None:
        crit.extend(["LARGER", str(larger_than)])
    if smaller_than is not None:
        crit.extend(["SMALLER", str(smaller_than)])

    if not crit:
        crit.append("ALL")

    if has_nonascii:
        return ["CHARSET", "UTF-8", *crit]
    return crit


def _uid_search(conn: imaplib.IMAP4, criteria: list[str | bytes] | str) -> list[bytes]:
    if isinstance(criteria, str):
        typ, data = conn.uid("SEARCH", None, criteria)  # type: ignore[arg-type]
    else:
        typ, data = conn.uid("SEARCH", *criteria)  # type: ignore[arg-type]
    if typ != "OK":
        raise ImapError(f"SEARCH failed: {data!r}")
    return (data[0] or b"").split()


def list_messages(
    cfg: ImapConfig,
    folder: str | None = None,
    limit: int = 50,
    search: str = "ALL",
) -> list[dict[str, Any]]:
    folder = folder or cfg.default_folder
    _reject_control_chars(folder, "folder")
    _reject_control_chars(search, "search")
    with _connect(cfg) as conn:
        _select(conn, folder, readonly=True)
        uids = _uid_search(conn, search)
        return _fetch_headers(conn, uids, limit)


def search_messages(
    cfg: ImapConfig,
    folder: str | None = None,
    limit: int = 50,
    **criteria: Any,
) -> list[dict[str, Any]]:
    """Structured search inside one IMAP folder.

    Accepts the same keyword arguments as `build_search_criteria`.
    """
    folder = folder or cfg.default_folder
    _reject_control_chars(folder, "folder")
    spec = build_search_criteria(**criteria)
    with _connect(cfg) as conn:
        _select(conn, folder, readonly=True)
        uids = _uid_search(conn, spec)
        return _fetch_headers(conn, uids, limit)


def _fetch_headers(conn: imaplib.IMAP4, uids: list[bytes], limit: int) -> list[dict[str, Any]]:
    # Newest last in IMAP search → reverse, take limit
    uids = list(reversed(uids))[: max(0, limit)]
    if not uids:
        return []
    uid_set = b",".join(uids).decode("ascii")
    typ, fdata = conn.uid(
        "FETCH",
        uid_set,
        "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID)] FLAGS RFC822.SIZE)",
    )
    if typ != "OK":
        raise ImapError("FETCH headers failed")
    return _parse_header_fetch(fdata)


def _parse_header_fetch(fdata: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in fdata:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        meta_raw, body_raw = item[0], item[1]
        meta = (
            meta_raw.decode("utf-8", errors="replace")
            if isinstance(meta_raw, bytes)
            else str(meta_raw)
        )
        uid = _extract(meta, "UID")
        size = _extract(meta, "RFC822.SIZE")
        flags = _extract_flags(meta)
        msg = email.message_from_bytes(
            body_raw if isinstance(body_raw, bytes) else body_raw.encode()
        )
        out.append(
            {
                "uid": uid,
                "size": int(size) if size and size.isdigit() else None,
                "flags": flags,
                "from": _decode(msg.get("From")),
                "to": _decode(msg.get("To")),
                "subject": _decode(msg.get("Subject")),
                "date": _decode(msg.get("Date")),
                "message_id": _decode(msg.get("Message-ID")),
            }
        )
    return out


def _extract(meta: str, key: str) -> str:
    # Crude but reliable: find `KEY VALUE` token in the metadata string.
    parts = meta.replace("(", " ").replace(")", " ").split()
    for i, p in enumerate(parts):
        if p == key and i + 1 < len(parts):
            return parts[i + 1]
    return ""


def _extract_flags(meta: str) -> list[str]:
    i = meta.find("FLAGS")
    if i < 0:
        return []
    j = meta.find("(", i)
    k = meta.find(")", j)
    if j < 0 or k < 0:
        return []
    return meta[j + 1 : k].split()


def fetch_message(
    cfg: ImapConfig,
    uid: str,
    folder: str | None = None,
    reader: bool = False,
) -> dict[str, Any]:
    folder = folder or cfg.default_folder
    _validate_uid(uid)
    _reject_control_chars(folder, "folder")
    with _connect(cfg) as conn:
        _select(conn, folder, readonly=True)
        typ, data = conn.uid("FETCH", uid, "(RFC822)")
        if typ != "OK" or not data or not isinstance(data[0], tuple):
            raise ImapError(f"could not fetch UID {uid}")
        raw = data[0][1]
        msg = email.message_from_bytes(raw if isinstance(raw, bytes) else raw.encode())
        return _serialize_message(msg, uid=uid, reader=reader)


def _serialize_message(
    msg: Message,
    uid: str | None = None,
    reader: bool = False,
) -> dict[str, Any]:
    body_text: str | None = None
    body_html: str | None = None
    attachments: list[dict[str, Any]] = []

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                payload = part.get_payload(decode=True) or b""
                attachments.append(
                    {
                        "index": len(attachments),
                        "filename": _decode(part.get_filename() or ""),
                        "content_type": ctype,
                        "size": len(payload),
                    }
                )
                continue
            if ctype == "text/plain" and body_text is None:
                body_text = _payload_str(part)
            elif ctype == "text/html" and body_html is None:
                body_html = _payload_str(part)
    else:
        ctype = msg.get_content_type()
        if ctype == "text/html":
            body_html = _payload_str(msg)
        else:
            body_text = _payload_str(msg)

    body_reader: str | None = None
    if reader:
        if body_html:
            body_reader = _html_to_reader(body_html)
        elif body_text:
            body_reader = body_text.strip() or None

    return {
        "uid": uid,
        "from": _decode(msg.get("From")),
        "to": _decode(msg.get("To")),
        "cc": _decode(msg.get("Cc")),
        "subject": _decode(msg.get("Subject")),
        "date": _decode(msg.get("Date")),
        "message_id": _decode(msg.get("Message-ID")),
        "references": _decode(msg.get("References")),
        "body_text": body_text,
        "body_html": body_html,
        "body_reader": body_reader,
        "attachments": attachments,
    }


def _payload_str(part: Message) -> str:
    raw = part.get_payload(decode=True)
    if not isinstance(raw, bytes):
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return raw.decode("utf-8", errors="replace")


def delete_message(
    cfg: ImapConfig, uid: str, folder: str | None = None, permanent: bool = False
) -> dict[str, Any]:
    """Move a message to the trash folder; erase it only when `permanent`.

    Deleting from the trash itself, or from a server with no trash folder,
    needs `permanent=True` — nothing is ever erased by surprise.
    """
    folder = folder or cfg.default_folder
    _validate_uid(uid)
    _reject_control_chars(folder, "folder")
    with _connect(cfg) as conn:
        trash = None if permanent else _find_trash(conn, cfg)
        if not permanent and (trash is None or trash == folder):
            raise ImapError(
                "no trash folder to move the message to (or it is already there); "
                "pass permanent=true to erase it"
            )
        _select(conn, folder, readonly=False)
        if trash is not None:
            if _has_capability(conn, "MOVE"):
                typ, _ = conn.uid("MOVE", uid, _quote(trash))
                if typ != "OK":
                    raise ImapError(f"UID MOVE to {trash!r} failed for UID {uid}")
                return {"ok": True, "moved_to": trash}
            typ, _ = conn.uid("COPY", uid, _quote(trash))
            if typ != "OK":
                raise ImapError(f"UID COPY to {trash!r} failed for UID {uid}")
        typ, _ = conn.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
        if typ != "OK":
            raise ImapError(f"STORE \\Deleted failed for UID {uid}")
        _expunge_uid(conn, uid)
        return {"ok": True, "moved_to": trash} if trash else {"ok": True, "erased": True}


def append_message(cfg: ImapConfig, folder: str, raw: bytes) -> None:
    """Store a copy of an outgoing message (already read: flagged \\Seen)."""
    with _connect(cfg) as conn:
        # typeshed declares append() as returning str; it returns (typ, data).
        response: Any = conn.append(
            _quote(folder), r"(\Seen)", imaplib.Time2Internaldate(time.time()), raw
        )
        if response[0] != "OK":
            raise ImapError(f"APPEND to {folder!r} failed")


def unified_search(
    mailboxes: list[MailboxConfig],
    folder: str | None = None,
    limit: int = 50,
    **criteria: Any,
) -> dict[str, Any]:
    """Fan-out search across multiple IMAP mailboxes.

    Each result message is tagged with `mailbox` (config name) and
    `mailbox_address` (IMAP login / email) so the caller can tell where
    it came from. Per-mailbox errors are collected in `errors` rather
    than aborting the whole call.
    """
    targets = [mb for mb in mailboxes if mb.imap is not None]
    if not targets:
        return {"messages": [], "errors": []}

    def _one(mb: MailboxConfig) -> tuple[str, list[dict[str, Any]], str | None]:
        imap = mb.imap
        if imap is None:
            return mb.name, [], "IMAP not configured"
        try:
            msgs = search_messages(imap, folder=folder, limit=limit, **criteria)
        except (ImapError, OSError) as e:
            return mb.name, [], str(e)
        for m in msgs:
            m["mailbox"] = mb.name
            m["mailbox_address"] = imap.username
        return mb.name, msgs, None

    merged: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, len(targets))) as ex:
        for name, msgs, err in ex.map(_one, targets):
            if err is not None:
                errors.append({"mailbox": name, "error": err})
                continue
            merged.extend(msgs)

    def _key(m: dict[str, Any]) -> float:
        try:
            return parsedate_to_datetime(m.get("date") or "").timestamp()
        except (TypeError, ValueError):
            return 0.0

    merged.sort(key=_key, reverse=True)
    return {"messages": merged[: max(0, limit)], "errors": errors}


def mark_seen(cfg: ImapConfig, uid: str, folder: str | None = None, seen: bool = True) -> None:
    folder = folder or cfg.default_folder
    _validate_uid(uid)
    _reject_control_chars(folder, "folder")
    flag_op = "+FLAGS" if seen else "-FLAGS"
    with _connect(cfg) as conn:
        _select(conn, folder, readonly=False)
        typ, _ = conn.uid("STORE", uid, flag_op, r"(\Seen)")
        if typ != "OK":
            raise ImapError(f"STORE \\Seen failed for UID {uid}")


def mailbox_status(cfg: ImapConfig, folder: str | None = None) -> dict[str, int]:
    """UIDNEXT, UIDVALIDITY and UNSEEN of a folder, without selecting it.

    One cheap round trip: this is what the new-mail watcher polls.
    """
    folder = folder or cfg.default_folder
    with _connect(cfg) as conn:
        typ, data = conn.status(_quote(folder), "(UIDNEXT UIDVALIDITY UNSEEN)")
        if typ != "OK" or not data or not data[0]:
            raise ImapError(f"STATUS failed for {folder!r}")
        raw = data[0].decode("utf-8", "replace") if isinstance(data[0], bytes) else str(data[0])
        out = {}
        for key in ("UIDNEXT", "UIDVALIDITY", "UNSEEN"):
            value = _extract(raw, key)
            out[key.lower()] = int(value) if value.isdigit() else 0
        return out


def headers_since(
    cfg: ImapConfig, first_uid: int, folder: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    """Headers of messages with UID >= first_uid, newest first."""
    folder = folder or cfg.default_folder
    _reject_control_chars(folder, "folder")
    with _connect(cfg) as conn:
        _select(conn, folder, readonly=True)
        uids = [u for u in _uid_search(conn, f"UID {int(first_uid)}:*") if int(u) >= first_uid]
        # `n:*` always matches the highest UID, even when it is below n.
        return _fetch_headers(conn, uids, limit)


def fetch_attachment(
    cfg: ImapConfig, uid: str, index: int, folder: str | None = None
) -> tuple[str, str, bytes]:
    """(filename, content type, bytes) of the index-th attachment of a message."""
    folder = folder or cfg.default_folder
    _validate_uid(uid)
    _reject_control_chars(folder, "folder")
    with _connect(cfg) as conn:
        _select(conn, folder, readonly=True)
        typ, data = conn.uid("FETCH", uid, "(BODY.PEEK[])")
        if typ != "OK" or not data or not isinstance(data[0], tuple):
            raise ImapError(f"could not fetch UID {uid}")
        raw = data[0][1]
    msg = email.message_from_bytes(raw if isinstance(raw, bytes) else raw.encode())
    seen = 0
    for part in msg.walk():
        if "attachment" not in (part.get("Content-Disposition") or "").lower():
            continue
        if seen == index:
            payload = part.get_payload(decode=True)
            blob = payload if isinstance(payload, bytes) else b""
            return _decode(part.get_filename() or "anexo"), part.get_content_type(), blob
        seen += 1
    raise ImapError(f"attachment {index} not found in UID {uid}")
