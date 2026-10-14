"""SMTP send."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Iterable

from .config import ImapConfig, SmtpConfig
from .imap_client import ImapError, append_message

_HEADER_FORBIDDEN = ("\r", "\n")


class SmtpError(Exception):
    """Raised when an SMTP send fails."""


def send(
    cfg: SmtpConfig,
    to: Iterable[str],
    subject: str,
    body_text: str | None = None,
    body_html: str | None = None,
    cc: Iterable[str] | None = None,
    bcc: Iterable[str] | None = None,
    from_address: str | None = None,
    reply_to: str | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
    copy_to: tuple[ImapConfig, str] | None = None,
) -> dict[str, object]:
    """Send one message. `in_reply_to` threads it under the original.

    `copy_to` is (imap, folder): after a successful send the message is
    appended there, so it shows up in Sent for everyone sharing the mailbox.
    A failed copy is reported, not raised — the mail has already gone out.
    """
    for value, field in ((in_reply_to, "in_reply_to"), (references, "references")):
        if value and any(ch in value for ch in _HEADER_FORBIDDEN):
            raise SmtpError(f"invalid {field}: line breaks are not allowed")
    to_list = list(to)
    if not to_list:
        raise SmtpError("`to` must contain at least one address")
    if body_text is None and body_html is None:
        raise SmtpError("must supply body_text and/or body_html")

    sender = from_address or cfg.from_address
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to_list)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    # Derive the Message-ID domain from the sender so it matches the From: header —
    # mismatched Message-ID domains are a strong spam signal.
    sender_domain = sender.split("@")[-1].strip(">").strip() if "@" in sender else None
    msg["Message-ID"] = make_msgid(domain=sender_domain) if sender_domain else make_msgid()
    # Masquerade as Thunderbird — providers' spam heuristics treat unknown/missing
    # User-Agent as suspicious; a well-known MUA string is a mild positive signal.
    msg["User-Agent"] = (
        "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Thunderbird/128.5.0"
    )
    if cc:
        msg["Cc"] = ", ".join(cc)
    if reply_to:
        msg["Reply-To"] = reply_to
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        # Clients thread on References; seed it with the parent when the caller
        # doesn't pass the full chain.
        msg["References"] = references or in_reply_to
    elif references:
        msg["References"] = references

    if body_text is not None:
        msg.set_content(body_text)
    if body_html is not None:
        if body_text is None:
            msg.set_content("This message requires an HTML-capable client.")
        msg.add_alternative(body_html, subtype="html")

    rcpts = to_list + list(cc or []) + list(bcc or [])

    try:
        if cfg.tls == "ssl":
            with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=30) as s:
                s.login(cfg.username, cfg.password)
                s.send_message(msg, to_addrs=rcpts)
        else:
            with smtplib.SMTP(cfg.host, cfg.port, timeout=30) as s:
                s.ehlo()
                if cfg.tls == "starttls":
                    s.starttls()
                    s.ehlo()
                if cfg.username:
                    s.login(cfg.username, cfg.password)
                s.send_message(msg, to_addrs=rcpts)
    except (smtplib.SMTPException, OSError) as e:
        raise SmtpError(f"send failed: {e}") from e

    result: dict[str, object] = {
        "from": str(msg["From"]),
        "to": str(msg["To"]),
        "subject": subject,
        "message_id": msg.get("Message-ID", ""),
    }
    if copy_to is not None:
        imap, folder = copy_to
        try:
            # Bcc never travels in the headers, but the sender's copy should
            # remember it, as any mail client's Sent folder does.
            if bcc:
                msg["Bcc"] = ", ".join(bcc)
            append_message(imap, folder, msg.as_bytes())
            result["copy_saved_to"] = folder
        except (ImapError, OSError) as e:
            result["copy_error"] = str(e)
    return result
