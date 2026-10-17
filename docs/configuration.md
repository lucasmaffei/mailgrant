# Configuration

The gateway reads one YAML file (`MAILGRANT_CONFIG`, default
`/etc/mailgrant/config.yaml`). Any string in it may say `${NAME}` to pull a
value from the environment, so passwords and tokens stay out of the file. On
platforms where mounting a file is awkward, put the whole file, base64-encoded,
in `MAILGRANT_CONFIG_B64` instead.

Check a config without starting the server: `mailgrant check`. It prints
who may touch what.

## A complete example

```yaml
agents:
  - name: support-bot
    token_sha256: "9f86d08…"          # from `mailgrant token`; or token: "${SUPPORT_TOKEN}"
    mailboxes: [contact]              # names, addresses, or "*"
    scopes: [read, mark, send]

mailboxes:
  - name: contact
    imap:
      host: mail.example.com          # port 993, tls ssl by default
      username: contact@example.com
      password: "${CONTACT_PASSWORD}"
    smtp:
      host: mail.example.com
      port: 465
      tls: ssl
      username: contact@example.com
      password: "${CONTACT_PASSWORD}"
      from_address: "Example <contact@example.com>"
      allowed_from: [sales@example.com]
      save_copy_to: Sent

web:                                  # optional, see [web-app.md](web-app.md)
  origin: https://mail.example.com
  data_dir: /data
  user: {name: owner, mailboxes: ["*"], scopes: [read, mark, delete, send]}
```

[`config.example.yaml`](../config.example.yaml) documents every option.

## Rules worth knowing

- Grants are checked at startup: a typo in an agent's `mailboxes` stops the server instead of silently granting nothing.
- The same token (or hash) on two agents is an error.
- `token_sha256` keeps the file free of usable secrets; `token: "${VAR}"` keeps it in the environment. Both work.
- `auth.tokens` (from docker-mailbox) still works and grants everything to everyone holding it. `mailgrant check` warns about it.
- Changing the config file needs a restart. With `web.manage: true`, mailboxes and agents live in the app instead and change without one.

## Mailbox options

| Key | Default | Notes |
|---|---|---|
| `imap.port` / `imap.tls` | `993` / `ssl` | `tls`: `ssl`, `starttls`, `none` |
| `imap.default_folder` | `INBOX` | |
| `imap.trash_folder` | auto | Folder flagged `\Trash`, then `Trash`, `Deleted Items`, `Lixeira` |
| `smtp.port` / `smtp.tls` | `587` / `starttls` | |
| `smtp.from_address` | — | Required. Default `From:` |
| `smtp.allowed_from` | `[]` | Other `From:` addresses callers may use |
| `smtp.save_copy_to` | — | IMAP folder that receives a copy of each sent message (needs `imap`) |

## Web app options

| Key | Default | Notes |
|---|---|---|
| `web.enabled` | `true` | `false` keeps the section but turns the app off |
| `web.origin` | — | Required. `https://host` (or `http://localhost` for tests) |
| `web.data_dir` | `/data` | SQLite; must persist across restarts |
| `web.user` | `owner`, `*`, all scopes | Granted like an agent |
| `web.poll_seconds` | `60` | How often new mail is checked for push |
| `web.session_days` | `30` | Sign-in lifetime on a device |
| `web.push_contact` | origin | `mailto:` or `https:` contact for push services |
| `web.manage` | `false` | Manage mailboxes and agents in the app; needs `MAILGRANT_SECRET_KEY`. See [web-app.md](web-app.md#manage-mailboxes-and-agents-in-the-app-optional) |
| `web.setup_code` | `MAILGRANT_SETUP_CODE` | Code typed on the sign-in screen to create the first passkey; dead once one exists |

## Audit log

With `audit_log: true` (default), every mail operation writes one line to the
`mailgrant.audit` logger on stdout:

```json
{"ts": "2026-10-14T22:01:08+00:00", "agent": "support-bot", "action": "get_message", "outcome": "ok", "mailbox": "contact", "uid": "42"}
{"ts": "2026-10-14T22:01:09+00:00", "agent": "support-bot", "action": "delete_message", "outcome": "denied", "reason": "scope", "mailbox": "contact"}
{"ts": "2026-10-14T22:01:10+00:00", "agent": "support-bot", "action": "send", "outcome": "ok", "mailbox": "contact", "to": ["client@example.com"], "message_id": "<…>"}
```

Subjects and bodies are never logged.

On Coolify, the application's **Logs** tab shows them; filter by
`mailgrant.audit`. Ship them elsewhere if you need retention. With the web app
on, the same events also make up each agent's timeline in the app.
