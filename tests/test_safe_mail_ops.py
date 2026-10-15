"""Delete goes to the trash, UIDs are single messages, sends thread and keep a copy."""

from __future__ import annotations

import email
from typing import Any
from unittest.mock import MagicMock

import pytest

from mailgrant import imap_client, smtp_client
from mailgrant.config import ImapConfig, SmtpConfig
from mailgrant.imap_client import ImapError, _parse_list

IMAP = ImapConfig(host="h", username="u@example.org", password="p")


class FakeConn:
    """Just enough of imaplib.IMAP4 to watch which commands delete issues."""

    def __init__(self, caps: str, folders: list[bytes]) -> None:
        self._caps = caps
        self._folders = folders
        self.calls: list[tuple[Any, ...]] = []

    def capability(self) -> tuple[str, list[bytes]]:
        return "OK", [self._caps.encode()]

    def list(self) -> tuple[str, list[bytes]]:
        return "OK", self._folders

    def select(self, mailbox: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        self.calls.append(("SELECT", mailbox))
        return "OK", [b"1"]

    def uid(self, command: str, *args: Any) -> tuple[str, list[bytes]]:
        self.calls.append((command, *args))
        return "OK", [b""]

    def expunge(self) -> tuple[str, list[bytes]]:  # must never be used
        self.calls.append(("BARE-EXPUNGE",))
        return "OK", [b""]


FOLDERS = [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Trash) "/" "Lixeira"']


def _patch(monkeypatch: pytest.MonkeyPatch, conn: FakeConn) -> None:
    cm = MagicMock()
    cm.__enter__.return_value = conn
    monkeypatch.setattr(imap_client, "_connect", lambda _cfg: cm)


def test_parse_list_handles_spaces_quotes_and_nil() -> None:
    lines = [
        b'(\\HasNoChildren) "/" "Caixa de entrada"',
        b"(\\Noselect) NIL INBOX",
        b'() "." "A \\"q\\" b"',
    ]
    assert [n for n, _ in _parse_list(lines)] == ["Caixa de entrada", "INBOX", 'A "q" b']


@pytest.mark.parametrize("uid", ["1:*", "3,4", "0", "1 2", "x"])
def test_ranges_and_junk_uids_are_refused(uid: str) -> None:
    with pytest.raises(ImapError, match="invalid uid"):
        imap_client.delete_message(IMAP, uid)


def test_delete_moves_to_trash_with_move(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn("IMAP4rev1 MOVE UIDPLUS", FOLDERS)
    _patch(monkeypatch, conn)
    assert imap_client.delete_message(IMAP, "9") == {"ok": True, "moved_to": "Lixeira"}
    assert ("MOVE", "9", '"Lixeira"') in conn.calls
    assert not any(c[0] in ("STORE", "EXPUNGE", "BARE-EXPUNGE") for c in conn.calls)


def test_delete_without_move_copies_then_expunges_only_that_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = FakeConn("IMAP4rev1 UIDPLUS", FOLDERS)
    _patch(monkeypatch, conn)
    imap_client.delete_message(IMAP, "9")
    commands = [c for c in conn.calls if c[0] != "SELECT"]
    assert commands == [
        ("COPY", "9", '"Lixeira"'),
        ("STORE", "9", "+FLAGS", r"(\Deleted)"),
        ("EXPUNGE", "9"),
    ]


def test_bare_expunge_is_never_used(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn("IMAP4rev1", FOLDERS)  # no MOVE, no UIDPLUS
    _patch(monkeypatch, conn)
    with pytest.raises(ImapError, match="UIDPLUS"):
        imap_client.delete_message(IMAP, "9", permanent=True)
    assert ("BARE-EXPUNGE",) not in conn.calls


def test_delete_from_trash_needs_permanent(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn("IMAP4rev1 MOVE UIDPLUS", FOLDERS)
    _patch(monkeypatch, conn)
    with pytest.raises(ImapError, match="permanent"):
        imap_client.delete_message(IMAP, "9", folder="Lixeira")
    assert imap_client.delete_message(IMAP, "9", folder="Lixeira", permanent=True) == {
        "ok": True,
        "erased": True,
    }
    assert ("EXPUNGE", "9") in conn.calls


def test_no_trash_folder_needs_permanent(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn("IMAP4rev1 MOVE UIDPLUS", [b'(\\HasNoChildren) "/" "INBOX"'])
    _patch(monkeypatch, conn)
    with pytest.raises(ImapError, match="no trash folder"):
        imap_client.delete_message(IMAP, "9")


def test_send_threads_reply_and_saves_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[email.message.EmailMessage] = []
    server = MagicMock()
    server.__enter__.return_value.send_message.side_effect = lambda msg, to_addrs: sent.append(msg)
    monkeypatch.setattr(smtp_client.smtplib, "SMTP_SSL", lambda *a, **k: server)
    appended: list[tuple[str, bytes]] = []
    monkeypatch.setattr(
        smtp_client, "append_message", lambda cfg, folder, raw: appended.append((folder, raw))
    )
    smtp = SmtpConfig(
        host="h", port=465, tls="ssl", username="u", password="p", from_address="u@example.org"
    )
    result = smtp_client.send(
        smtp,
        to=["a@example.com"],
        subject="Re: hi",
        body_text="ok",
        bcc=["hidden@example.com"],
        in_reply_to="<parent@example.com>",
        copy_to=(IMAP, "Sent"),
    )
    assert sent[0]["In-Reply-To"] == "<parent@example.com>"
    assert sent[0]["References"] == "<parent@example.com>"
    assert result["copy_saved_to"] == "Sent"
    copy = email.message_from_bytes(appended[0][1])
    assert copy["Bcc"] == "hidden@example.com"


def test_send_rejects_header_injection() -> None:
    smtp = SmtpConfig(host="h", username="u", password="p", from_address="u@example.org")
    with pytest.raises(smtp_client.SmtpError, match="line breaks"):
        smtp_client.send(smtp, to=["a@x"], subject="s", body_text="b", in_reply_to="<a>\r\nBcc: x")


def test_failed_copy_is_reported_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtp_client.smtplib, "SMTP_SSL", lambda *a, **k: MagicMock())

    def boom(*_a: Any) -> None:
        raise ImapError("APPEND failed")

    monkeypatch.setattr(smtp_client, "append_message", boom)
    smtp = SmtpConfig(
        host="h", port=465, tls="ssl", username="u", password="p", from_address="u@example.org"
    )
    result = smtp_client.send(smtp, to=["a@x"], subject="s", body_text="b", copy_to=(IMAP, "Sent"))
    assert result["copy_error"] == "APPEND failed"


def test_envelope_uses_bare_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    server = MagicMock()
    server.__enter__.return_value.send_message.side_effect = lambda msg, to_addrs: calls.append(
        to_addrs
    )
    monkeypatch.setattr(smtp_client.smtplib, "SMTP_SSL", lambda *a, **k: server)
    smtp = SmtpConfig(
        host="h", port=465, tls="ssl", username="u", password="p", from_address="u@example.org"
    )
    smtp_client.send(
        smtp,
        to=["Mariana Duarte <m@example.com>"],
        cc=["Recepção <r@example.com>"],
        bcc=["b@example.com"],
        subject="s",
        body_text="b",
        attachments=[("a.pdf", "application/pdf", b"%PDF")],
    )
    assert calls == [["m@example.com", "r@example.com", "b@example.com"]]


@pytest.mark.parametrize("uids", [["1:*"], ["3,4"], []])
def test_batches_still_refuse_ranges(uids: list[str]) -> None:
    with pytest.raises(ImapError):
        imap_client.set_flags(IMAP, uids, "seen", True)


class DraftConn(FakeConn):
    def __init__(self, flags: bytes) -> None:
        super().__init__("IMAP4rev1 UIDPLUS", FOLDERS)
        self._flags = flags
        self.created: list[str] = []

    def uid(self, command: str, *args: Any) -> tuple[str, list[bytes]]:
        self.calls.append((command, *args))
        if command == "FETCH":
            return "OK", [b"1 (UID 5 FLAGS (" + self._flags + b"))"]
        return "OK", [b""]

    def create(self, name: str) -> tuple[str, list[bytes]]:
        self.created.append(name)
        return "OK", [b""]

    def subscribe(self, name: str) -> tuple[str, list[bytes]]:
        return "OK", [b""]


def test_delete_draft_only_erases_drafts(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = DraftConn(b"\\Seen")
    _patch(monkeypatch, conn)
    with pytest.raises(ImapError, match="not a draft"):
        imap_client.delete_draft(IMAP, "5", "Drafts")
    assert not any(c[0] in ("STORE", "EXPUNGE") for c in conn.calls)
    conn = DraftConn(b"\\Seen \\Draft")
    _patch(monkeypatch, conn)
    imap_client.delete_draft(IMAP, "5", "Drafts")
    assert ("EXPUNGE", "5") in conn.calls


def test_archive_creates_the_folder_and_moves_the_set(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = DraftConn(b"")
    conn._caps = "IMAP4rev1 MOVE UIDPLUS"
    _patch(monkeypatch, conn)
    result = imap_client.move_to(IMAP, ["7", "9", "7"], "archive")
    assert conn.created == ['"Archive"']
    assert result == {"ok": True, "moved_to": "Archive", "count": 2}
    assert ("MOVE", "7,9", '"Archive"') in conn.calls


def test_thread_search_covers_every_id() -> None:
    crit = imap_client._thread_criteria(["<a@x>", "<b@y>"])
    assert crit.count("OR") == 5
    assert crit.count('"<a@x>"') == 3 and crit.count('"<b@y>"') == 3
    assert imap_client.message_ids("<a@x> <b@y>", "<a@x>", None) == ["<a@x>", "<b@y>"]


def test_folded_references_come_back_on_one_line() -> None:
    raw = (
        b"From: a@x.org\r\nSubject: Re: s\r\nMessage-ID: <c@x>\r\n"
        b"In-Reply-To: <b@x>\r\nReferences: <a@x>\r\n <b@x>\r\n\r\nbody\r\n"
    )
    msg = imap_client._serialize_message(email.message_from_bytes(raw), uid="1")
    assert msg["references"] == "<a@x> <b@x>"
    # ... so a reply built from it passes the header-injection check.
    built = smtp_client.build_message(
        "u@x.org", ["a@x.org"], "Re: s", "ok", in_reply_to="<c@x>", references=msg["references"]
    )
    assert built["References"] == "<a@x> <b@x>"
