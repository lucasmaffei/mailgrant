<p align="center"><img alt="mailgrant — one email gateway for people and AI agents, each with its own mailboxes and permissions" src="docs/assets/hero.png" width="1280"></p>

<p>
  <a href="https://github.com/lucasmaffei/mailgrant/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/lucasmaffei/mailgrant/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="MCP: Streamable HTTP" src="https://img.shields.io/badge/MCP-Streamable%20HTTP-38cfff?labelColor=05090b">
  <img alt="Web app: PWA with passkeys" src="https://img.shields.io/badge/web%20app-PWA%20%2B%20passkeys-38cfff?labelColor=05090b">
  <img alt="Docker image on GHCR" src="https://img.shields.io/badge/docker-ghcr.io%2Flucasmaffei%2Fmailgrant-0b1114?logo=docker&logoColor=white&labelColor=05090b">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-0b1114?labelColor=05090b"></a>
</p>

[Português](README.pt-BR.md) · [Web app](docs/web-app.md) · [Deploy on Coolify](docs/deploy-coolify.md) · [Connect your agents](docs/connect-agents.md) · [Changelog](CHANGELOG.md)

mailgrant sits between your IMAP/SMTP mailboxes and everyone who works with
them. You register every mailbox **once**, then decide who gets which
mailboxes and which actions:

- **Agents** get a bearer token and talk MCP (Streamable HTTP) or REST.
- **You** get an optional web app: one inbox on your phone or computer, signed
  in with a passkey, with push notifications and a timeline of what every
  agent did.

Every call from either side goes through the same grants and the same audit log.

<p align="center"><img alt="Who uses it, the gateway, and your mailboxes" src="docs/assets/how-it-works.png" width="1280"></p>

## Why

Agents multiply, and so do mailboxes. Without a gateway every agent holds its
own copy of every password, on its own server, in its own harness. Adding a
mailbox means visiting every agent; revoking access means hoping you found all
the copies. And you still need somewhere to read the same mail yourself.

With mailgrant:

- **A new mailbox** is one entry in one file. Agents granted `"*"` see it right away.
- **Revoking** an agent is deleting its token. Mailbox passwords never leave the gateway.
- **Least privilege is real**: a read-only agent can't send, delete or even mark as read, and doesn't see those tools at all.
- **You see what they did**: every read, send and refusal, in the log and in the app.

## Features

- **Per-agent grants**: mailboxes by name, address or `*`; scopes `read`, `mark`, `delete`, `send`.
- **Invisible outside the grant**: a mailbox an agent can't use answers exactly like one that doesn't exist.
- **Scoped tool list**: MCP `tools/list` only shows the tools a token may call.
- **Unified inbox**: one call searches every granted mailbox in parallel.
- **Safe delete**: moves to the trash; erasing needs `permanent=true` and touches one message only.
- **Threaded replies** with `in_reply_to`, and a copy of every sent message in the Sent folder.
- **No spoofing**: `from_address` limited to the mailbox's own address and declared aliases.
- **Audit log**: metadata only, never subjects or bodies.
- **Optional web app**: installable PWA, passkey sign-in, push notifications, agent activity. Off unless configured.
- **Stateless without the web app**: no database; connections open per request and close.
- **Secrets from the environment**: `${VAR}` anywhere, or the whole config in `MAILGRANT_CONFIG_B64`.

## Use cases

| Case | Mailboxes | Scopes |
|---|---|---|
| **Customer support.** An agent answers the contact address inside the original thread, and the reply lands in Sent for the team to see. | `contact@` | `read`, `mark`, `send` |
| **Finance.** An agent reads invoices and receipts to reconcile payments. It can't reply or delete anything. | `billing@` | `read` |
| **Daily digest.** A scheduled script summarizes what arrived unread in every mailbox each morning. | `*` | `read` |
| **Personal assistant.** Triages your own inbox: marks what you've seen, trashes newsletters, answers the routine. | `you@` | `read`, `mark`, `delete`, `send` |
| **Agency with many clients.** Each client's agent reaches only that client's mailboxes, even on the same server. | `client-a@`, `billing@client-a` | `read`, `send` |
| **Lead intake.** A sales agent reads website form notifications and answers new leads from `sales@`, and sees nothing else. | `sales@` | `read`, `send` |

In every case, rotating a mailbox password, cutting an agent off or adding a
new mailbox is a change to the gateway. No agent has to be touched.

## The web app (optional)

<p align="center"><img alt="Inbox, message, agents and settings on a phone" src="docs/assets/screens.png" width="1280"></p>

A small app for the person who owns the mailboxes. It is **off by default**;
add a `web:` section to turn it on:

```yaml
web:
  origin: https://mail.example.com     # where you open it
  data_dir: /data                       # SQLite for passkeys, push devices, history
  user: {name: lucas, mailboxes: ["*"], scopes: [read, mark, delete, send]}
```

Then create your first passkey, either way:

- `mailgrant invite` prints a one-time link to open on your phone, or
- set `MAILGRANT_SETUP_CODE` in the environment (12+ characters) and type it
  on the sign-in screen. It only works until the first passkey exists.

Then add the app to the Home Screen and turn notifications on.

- **Turn it off** by removing the section or setting `enabled: false`. `/app`
  disappears and nothing is polled; agents are not affected.
- The person is granted like an agent, so a read-only phone is one line.
- Optionally (`manage: true`) it also manages the mailboxes and each agent's
  permissions and tokens, live, with the passkey asked again for every change.
- It is a real mail client: conversations, reply all, forward, Cc/Bcc,
  attachments, drafts saved to the mailbox's Drafts folder, signatures, stars,
  archive, batch actions and swipe gestures on the phone.
- Mail bodies are shown as text, attachments always download, and a strict
  CSP keeps every resource on your own origin.
- The interface is in Brazilian Portuguese for now.

<p align="center"><img alt="The web app on a computer" src="docs/assets/desktop.png" width="1100"></p>

Full guide: **[docs/web-app.md](docs/web-app.md)** (install on iPhone,
notifications, what is stored, security model, turning it off).

## Quick start

```bash
git clone https://github.com/lucasmaffei/mailgrant && cd mailgrant
cp config.example.yaml config.yaml

# 1. Mint a token per agent. Give the token to the agent; keep the hash.
docker run --rm ghcr.io/lucasmaffei/mailgrant:latest mailgrant token --name support-bot

# 2. Edit config.yaml: your mailboxes, the agents with their hashes,
#    and the `web:` section if you want the app.
# 3. Validate it — prints who may touch what.
docker run --rm -v "$PWD/config.yaml:/etc/mailgrant/config.yaml:ro" \
  ghcr.io/lucasmaffei/mailgrant:latest mailgrant check

# 4. Run it (published on loopback; put TLS in front before exposing it).
docker compose up -d
curl -s http://127.0.0.1:8000/health
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/whoami

# 5. Web app only: a one-time link to create your passkey
#    (or set MAILGRANT_SETUP_CODE and type it on the sign-in screen).
docker compose exec mailgrant mailgrant invite
```

No registry access yet? `docker compose up -d --build` builds from the checkout.

## Configuration

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

web:                                  # optional — see "The web app"
  origin: https://mail.example.com
  data_dir: /data
  user: {name: owner, mailboxes: ["*"], scopes: [read, mark, delete, send]}
```

[`config.example.yaml`](config.example.yaml) documents every option.

### Scopes

| Scope | MCP tools | REST |
|---|---|---|
| — | `whoami` | `GET /whoami` |
| `read` | `mailboxes`, `inbox`, `list_folders`, `list_messages`, `search`, `get_message` | `GET /mailboxes`, `/inbox`, `/mailboxes/{name}/…` |
| `mark` | `mark_seen` | `POST /mailboxes/{name}/messages/{uid}/seen` |
| `delete` | `delete_message` | `DELETE /mailboxes/{name}/messages/{uid}` |
| `send` | `send` | `POST /mailboxes/{name}/send` |

Reading never changes a message: folders are opened read-only (`EXAMINE`), so
the Seen flag stays as the humans left it.

### Rules worth knowing

- Grants are checked at startup: a typo in an agent's `mailboxes` stops the server instead of silently granting nothing.
- The same token (or hash) on two agents is an error.
- `token_sha256` keeps the file free of usable secrets; `token: "${VAR}"` keeps it in the environment. Both work.
- `auth.tokens` (from docker-mailbox) still works and grants everything to everyone holding it. `mailgrant check` warns about it.
- Changing the config needs a restart.

### Mailbox options

| Key | Default | Notes |
|---|---|---|
| `imap.port` / `imap.tls` | `993` / `ssl` | `tls`: `ssl`, `starttls`, `none` |
| `imap.default_folder` | `INBOX` | |
| `imap.trash_folder` | auto | Folder flagged `\Trash`, then `Trash`, `Deleted Items`, `Lixeira` |
| `smtp.port` / `smtp.tls` | `587` / `starttls` | |
| `smtp.from_address` | — | Required. Default `From:` |
| `smtp.allowed_from` | `[]` | Other `From:` addresses callers may use |
| `smtp.save_copy_to` | — | IMAP folder that receives a copy of each sent message (needs `imap`) |

### Web app options

| Key | Default | Notes |
|---|---|---|
| `web.enabled` | `true` | `false` keeps the section but turns the app off |
| `web.origin` | — | Required. `https://host` (or `http://localhost` for tests) |
| `web.data_dir` | `/data` | SQLite; must persist across restarts |
| `web.user` | `owner`, `*`, all scopes | Granted like an agent |
| `web.poll_seconds` | `60` | How often new mail is checked for push |
| `web.session_days` | `30` | Sign-in lifetime on a device |
| `web.push_contact` | origin | `mailto:` or `https:` contact for push services |
| `web.manage` | `false` | Manage mailboxes and agents in the app; needs `MAILGRANT_SECRET_KEY`. See [docs/web-app.md](docs/web-app.md#manage-mailboxes-and-agents-in-the-app-optional) |
| `web.setup_code` | `MAILGRANT_SETUP_CODE` | Code typed on the sign-in screen to create the first passkey; dead once one exists |

## Connecting agents

Any MCP client that supports Streamable HTTP with a bearer header works.
Full walkthrough: **[docs/connect-agents.md](docs/connect-agents.md)**.

```bash
# Claude Code
claude mcp add --transport http mailgrant https://mail-mcp.example.com/mcp \
  --header "Authorization: Bearer $MAILGRANT_TOKEN"

# Codex
codex mcp add mailgrant --url https://mail-mcp.example.com/mcp \
  --bearer-token-env-var MAILGRANT_TOKEN

# Anything that only launches stdio servers (OpenClaw, older clients)
npx -y mcp-remote@0.1.38 https://mail-mcp.example.com/mcp \
  --transport http-only --header "Authorization: Bearer $MAILGRANT_TOKEN"
```

Give your agents the skill in [`.agents/skills/mailgrant/SKILL.md`](.agents/skills/mailgrant/SKILL.md):
it teaches them to check `whoami` first, reply inside threads and confirm before deleting.

### Let the agent set itself up

Mint the agent's token, put it in the `MAILGRANT_TOKEN` environment variable
where the agent runs, and paste this prompt into a conversation with it (swap
in your URL):

```text
Connect yourself to my mailgrant email gateway.

- MCP endpoint: https://mail-mcp.example.com/mcp
- Your token is in the MAILGRANT_TOKEN environment variable. Never print it,
  never write it to a file in plain text, and never send it anywhere except the
  Authorization header of that endpoint.

Steps:
1. Work out which agent harness you're running in and add a remote MCP server
   named "mailgrant" with the URL above and the header
   "Authorization: Bearer <token>":
   - Claude Code: claude mcp add --scope user --transport http mailgrant <url> --header "Authorization: Bearer $MAILGRANT_TOKEN"
   - Codex: codex mcp add mailgrant --url <url> --bearer-token-env-var MAILGRANT_TOKEN
   - Anything else: register it in your MCP config as a Streamable HTTP server
     with that header. If you can only launch stdio servers, use
     npx -y mcp-remote@0.1.38 <url> --transport http-only --header "Authorization:${AUTH_HEADER}"
     with AUTH_HEADER="Bearer <token>" in the process env.
2. Install the usage skill from
   https://github.com/lucasmaffei/mailgrant/tree/main/.agents/skills/mailgrant
   (Claude Code: ~/.claude/skills/mailgrant/SKILL.md). If you can't install
   skills, read the file and follow its rules.
3. Reload your MCP servers if your harness needs it, then call the whoami tool.
4. Tell me which agent you are, your scopes, the mailboxes you can use and how
   many unread messages each one has (inbox with unseen=true). Don't mark
   anything as read, delete or send anything.
```

If the agent answers with its own name, scopes and the right mailboxes, it's
ready. A `401` means the token doesn't match any hash in the config.

## REST API

All routes except `/health` need `Authorization: Bearer <token>`.

| Method | Path | Scope | Does |
|---|---|---|---|
| `GET` | `/health` | — | Liveness, always open |
| `GET` | `/whoami` | — | This token's agent, scopes and mailboxes |
| `GET` | `/mailboxes` | read | Granted mailboxes |
| `GET` | `/inbox` | read | Unified search across granted mailboxes |
| `GET` | `/mailboxes/{name}/folders` | read | IMAP folders |
| `GET` | `/mailboxes/{name}/messages?folder=&limit=&search=` | read | Newest-first headers (raw IMAP search) |
| `GET` | `/mailboxes/{name}/search?from=&subject=&…` | read | Structured search in one mailbox |
| `GET` | `/mailboxes/{name}/messages/{uid}?folder=&reader=` | read | Full message; `reader=true` adds `body_reader` |
| `POST` | `/mailboxes/{name}/messages/{uid}/seen` | mark | Body `{"seen": true\|false}` |
| `DELETE` | `/mailboxes/{name}/messages/{uid}?folder=&permanent=` | delete | Move to trash, or erase |
| `POST` | `/mailboxes/{name}/send` | send | Send (see below) |

`{name}` also accepts the mailbox address. `/inbox` and `/search` take `from`,
`to`, `subject`, `body`, `text`, `since`, `before` (IMAP dates like
`14-Oct-2026`), `unseen`, `seen`, `flagged`, `answered`, `larger_than`,
`smaller_than`, `folder` and `limit` (≤ 500); `/inbox` also takes `mailbox`
(CSV of names or addresses). The OpenAPI schema is at `/openapi.json` (token required).

Send body:

```json
{
  "to": ["client@example.com"], "cc": [], "bcc": [],
  "subject": "Re: Order 42",
  "body_text": "…", "body_html": null,
  "in_reply_to": "<original-message-id@example.com>",
  "references": null, "reply_to": null, "from_address": null
}
```

Errors are JSON `{"detail": "…"}`: `401` bad or missing token · `403` scope
missing or `from_address` not allowed · `404` mailbox unknown **or not
granted** · `409` mailbox lacks IMAP/SMTP · `502` the mail server refused.

## Audit log

With `audit_log: true` (default), every mail operation writes one line to the
`mailgrant.audit` logger on stdout:

```json
{"ts": "2026-10-14T22:01:08+00:00", "agent": "support-bot", "action": "get_message", "outcome": "ok", "mailbox": "contact", "uid": "42"}
{"ts": "2026-10-14T22:01:09+00:00", "agent": "support-bot", "action": "delete_message", "outcome": "denied", "reason": "scope", "mailbox": "contact"}
{"ts": "2026-10-14T22:01:10+00:00", "agent": "support-bot", "action": "send", "outcome": "ok", "mailbox": "contact", "to": ["client@example.com"], "message_id": "<…>"}
```

Subjects and bodies are never logged.

## Security

- **Run it behind TLS.** Tokens and mail travel through it. Compose binds `127.0.0.1` by default; expose it only through an HTTPS reverse proxy.
- **The config holds mailbox passwords.** Prefer `${VAR}` references or `MAILGRANT_CONFIG_B64` from your platform's secret store; never commit a filled-in `config.yaml`.
- **Tokens are compared in constant time**, and every candidate is compared on every request.
- **IMAP command injection** is blocked at the boundary: control characters in folder names are rejected, folder names are quoted, UIDs are digits only.
- **Delete never erases by surprise**: trash first, `UID EXPUNGE` for exactly one message, refusal on servers without UIDPLUS.
- **The web app** signs in with passkeys only, keeps sessions in `HttpOnly`/`SameSite=Strict` cookies, checks `Origin` on every change and serves a CSP that loads nothing from other origins. Details in [docs/web-app.md](docs/web-app.md#security-model).
- **A token is only as narrow as its grant.** Give agents the fewest mailboxes and scopes that do the job; reserve `"*"` for agents you'd trust with all of them.

## Running from source

```bash
uv sync --all-groups
uv run mailgrant check --config config.yaml
uv run mailgrant http --config config.yaml   # binds 127.0.0.1:8000
uv run pytest -q
```

The README art and screenshots are generated from [`docs/assets/src`](docs/assets/src).

## Credits

mailgrant is a fork of [docker-mailbox](https://github.com/psyb0t/docker-mailbox)
by Ciprian Mandache (psyb0t), which provides the IMAP/SMTP layer, the unified
inbox, reader mode and the MCP transport. mailgrant adds per-agent grants,
auditing, safe deletion, threaded sending and the web app.

## License

MIT — see [LICENSE](LICENSE). The Docker image bundles third-party components
under their own licenses (html2text is GPL-3.0; the web app's fonts are OFL);
see [THIRD_PARTY.md](THIRD_PARTY.md).
