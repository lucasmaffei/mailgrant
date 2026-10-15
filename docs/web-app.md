# The web app

[Português](web-app.pt-BR.md)

mailgrant can also serve a small web app for **you**: one inbox across your
mailboxes, what each agent read and sent, and push notifications on your
phone. It installs to the home screen like an app, and you sign in with a
passkey (Face ID, Touch ID, Windows Hello, a security key) — there is no
password.

It is **off unless you turn it on**. Without a `web:` section in the config,
mailgrant stays a stateless MCP/REST gateway: no web routes, no database, no
extra dependencies loaded.

> The interface is in Brazilian Portuguese for now.

![The web app on a phone](assets/screens.png)

## What you get

| Screen | What it does |
|---|---|
| Inbox | Every mailbox you can see, newest first, filter by mailbox, search. Each message shows which agent already read or answered it. |
| Message | The body as clean text (HTML is converted, never rendered), attachments to download, the agents that touched it. Reply stays in the thread and is filed in Sent. |
| Agents | The audit trail as a timeline: reads, sends, trash moves, and every refusal — filter by sends or by refusals. |
| Settings | Turn notifications on, pick which mailboxes notify, get a push when an agent sends mail, manage passkeys, see each agent's access. |

On a computer it becomes three columns: mailboxes, list, message.

![The web app on a computer](assets/desktop.png)

## Turn it on

Add a `web:` section to the config:

```yaml
web:
  origin: https://mail.example.com        # the public URL people open
  data_dir: /data                          # SQLite: passkeys, push devices, history
  user:
    name: lucas
    mailboxes: ["*"]                       # like an agent: names, addresses or "*"
    scopes: [read, mark, delete, send]
  # poll_seconds: 60                       # how often new mail is checked
  # session_days: 30
  # push_contact: mailto:you@example.com   # contact for push services; default: origin
```

- `origin` must be `https://` (passkeys and push only work on secure origins;
  `http://localhost` is accepted for testing). Requests from any other origin
  are refused.
- `user` is granted exactly like an agent. Give yourself fewer scopes if you
  want a read-only phone.
- `data_dir` must be persistent (a Docker volume). It holds no mail.

Restart, then check it:

```bash
mailgrant check
# web app: on at https://mail.example.com/app for lucas [delete, mark, read, send]  all mailboxes; data in /data
```

## Your first passkey

Nobody can sign in until a device has a passkey, and a passkey can only be
created through a one-time invite. On the server:

```bash
mailgrant invite            # valid 30 minutes, one use
# https://mail.example.com/app/#/invite/Lweu52CZ…
```

In Docker: `docker compose exec mailgrant mailgrant invite`. On Coolify, use
the application's **Terminal** tab.

Open the link on the phone or computer that will hold the passkey, name the
device and confirm with Face ID / Touch ID. You are in.

**More devices:** in the app, **Ajustes → Adicionar outro aparelho** creates a
new invite to open on the other device. A signed-in device can also register
another passkey for itself. The last passkey can't be removed, so you can't
lock yourself out by accident; if you lose every device, run `mailgrant invite`
on the server again.

## Install it and turn on notifications

**iPhone / iPad (iOS 16.4 or later)** — notifications only work for the app
added to the Home Screen:

1. Open the URL in Safari, tap **Share → Add to Home Screen**.
2. Open mailgrant from the new icon (not from Safari).
3. **Ajustes → Ativar notificações**, and allow when iOS asks.

**Android / desktop Chrome, Edge, Firefox** — open the URL, sign in,
**Ajustes → Ativar notificações**. Chrome and Edge also offer **Install app**.

Then choose which mailboxes notify. **Testar** sends a test push to every
device that turned notifications on.

### How new mail is detected

Every `poll_seconds` (60 by default) mailgrant asks each mailbox for its
`STATUS` — one cheap command, no download — and pushes only the messages that
arrived since the last check, already unread. The first check after a start
only records where each mailbox is, so a restart never replays old mail. With
several workers, only one process watches (a lock file in `data_dir`).

A push carries the sender's name and the subject, and the unread count for the
app icon badge. It travels encrypted end-to-end (Web Push, RFC 8291) through
the browser vendor's push service (Apple, Google, Mozilla).

## What is stored, and where

In `data_dir/mailgrant.db` (SQLite):

- passkey public keys and device names — never a private key;
- sessions (a hash of the cookie), invites (a hash), WebAuthn challenges (minutes);
- push subscriptions and your notification choices;
- the push signing key (VAPID), created on first use;
- the audit history for the Agents screen: agent, action, mailbox, UID,
  recipients, outcome — never subjects or bodies — kept 180 days;
- the watcher's position in each mailbox.

Mail itself stays on your IMAP servers.

## Security model

- **Passkeys only.** WebAuthn with user verification required. No passwords,
  no recovery email.
- **Invites are one-time and expire.** Stored hashed.
- **Session cookie** is random, `HttpOnly`, `Secure`, `SameSite=Strict`,
  scoped to `/app`. Every change also needs an `X-Mailgrant` header and a
  matching `Origin`.
- **Same rules as agents.** The signed-in person is a principal granted by
  `web.user`; every action goes through the same grant checks and the same
  audit log.
- **Mail is text.** Bodies are rendered as text (links made clickable), HTML
  is never interpreted, attachments always download.
- **Strict CSP**: nothing loads from other origins — fonts are bundled, no
  inline scripts or styles, no frames.
- Agents' bearer tokens don't open the web app, and the web session doesn't
  open the MCP/REST API.

## Turn it off

Either remove the `web:` section, or keep it and set:

```yaml
web:
  enabled: false
  origin: https://mail.example.com
```

Restart. `/app` disappears, nothing is polled, the database is left untouched
(delete `data_dir` if you want it gone). Agents are not affected either way.

## Troubleshooting

| Symptom | Cause |
|---|---|
| "invite missing, used or expired" | Invites work once, for 30 minutes. Run `mailgrant invite` again. |
| Passkey prompt fails right away | The page isn't on the configured `origin` (another host, or http). |
| No "Ativar notificações" on iPhone | Open the app from the Home Screen icon, not from Safari. |
| Notifications stop on one device | The push service dropped the subscription (app removed, permission revoked). Turn them on again on that device. |
| New mail never notifies | The mailbox is switched off in Ajustes, or `poll_seconds` is long; check the logs for `watcher:` warnings. |
| Agents screen is empty | Agent history starts when the web app is turned on; earlier activity is only in the logs. |
