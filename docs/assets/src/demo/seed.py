"""Fill the demo mailboxes for one language: python3 seed.py <lang> (default en)."""
import imaplib
import os
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime

from content import CONTENT

lang = sys.argv[1] if len(sys.argv) > 1 else "en"
C = CONTENT[lang]
now = datetime.now(timezone(timedelta(hours=-3)))
if now.hour < 12:
    now -= timedelta(days=1)  # keep 'today' in the past


def at(days, h, m):
    return (now - timedelta(days=days)).replace(hour=h, minute=m, second=0, microsecond=0)


def login(user):
    c = imaplib.IMAP4("127.0.0.1", int(os.environ.get("DEMO_IMAP_PORT", "31144")))
    c.login(user, "pass")
    return c


for box, msgs in C["mail"].items():
    user = C["boxes"][box]
    c = login(user)
    for i, (frm, subj, days, h, m, seen, body) in enumerate(sorted(msgs, key=lambda x: at(*x[2:5]))):
        when = at(days, h, m)
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = frm, user, subj
        msg["Date"], msg["Message-ID"] = format_datetime(when), f"<demo{i}.{user}>"
        msg.set_content(body)
        c.append("INBOX", "(\\Seen)" if seen else "", imaplib.Time2Internaldate(when.timestamp()), msg.as_bytes())
    c.logout()

# A conversation: the clinic's question, the answer in Sent, a follow-up with an attachment.
user = C["boxes"]["contact"]
clinic = sorted(C["mail"]["contact"], key=lambda x: at(*x[2:5]))[2]
root = f"<demo2.{user}>"
c = login(user)
names = {f.decode().rsplit(" ", 1)[-1].strip('"') for f in c.list()[1]}
for f in ("Sent", "Drafts", "Trash", "Archive"):
    if f not in names:
        c.create(f)
r = EmailMessage()
r["From"], r["To"], r["Subject"] = user, clinic[0], "Re: " + clinic[1]
r["Date"], r["Message-ID"] = format_datetime(at(0, 10, 2)), f"<reply1.{user}>"
r["In-Reply-To"], r["References"] = root, root
r.set_content(C["answer"])
c.append("Sent", "(\\Seen)", imaplib.Time2Internaldate(at(0, 10, 2).timestamp()), r.as_bytes())
text, cc, filename = C["follow"]
f = EmailMessage()
f["From"], f["To"], f["Cc"], f["Subject"] = clinic[0], user, cc, "Re: " + clinic[1]
f["Date"], f["Message-ID"] = format_datetime(at(0, 10, 48)), f"<follow1.{user}>"
f["In-Reply-To"], f["References"] = f"<reply1.{user}>", f"{root} <reply1.{user}>"
f.set_content(text)
f.add_attachment(b"%PDF-1.4\n% demo\n" * 40, maintype="application", subtype="pdf", filename=filename)
c.append("INBOX", "", imaplib.Time2Internaldate(at(0, 10, 48).timestamp()), f.as_bytes())
c.logout()
print("seeded", lang)
