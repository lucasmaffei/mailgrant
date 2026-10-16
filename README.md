<p align="center"><img alt="mailgrant logo" src="src/mailgrant/web/static/icons/icon-192.png" width="88"></p>

<h1 align="center">mailgrant</h1>

<p align="center"><b>The self-hosted email gateway for AI agents.</b><br>
One MCP and REST endpoint in front of your IMAP/SMTP mailboxes: every agent gets its own token, its own mailboxes and its own permissions, and you get a webmail app to read along.</p>

<p align="center">
  <a href="https://github.com/lucasmaffei/mailgrant/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/lucasmaffei/mailgrant/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="MCP: Streamable HTTP" src="https://img.shields.io/badge/MCP-Streamable%20HTTP-38cfff?labelColor=05090b">
  <img alt="Web app: PWA with passkeys" src="https://img.shields.io/badge/web%20app-PWA%20%2B%20passkeys-38cfff?labelColor=05090b">
  <img alt="Docker image on GHCR" src="https://img.shields.io/badge/docker-ghcr.io%2Flucasmaffei%2Fmailgrant-0b1114?logo=docker&logoColor=white&labelColor=05090b">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-0b1114?labelColor=05090b"></a>
</p>

<p align="center"><b>English</b> · <a href="README.pt-BR.md">Português</a> · <a href="README.es.md">Español</a> · <a href="README.fr.md">Français</a> · <a href="README.zh-CN.md">简体中文</a></p>

<p align="center"><img alt="mailgrant: one email gateway for people and AI agents, each with its own mailboxes and permissions" src="docs/assets/hero.png" width="1280"></p>

Claude, Codex, OpenClaw, Hermes, your own scripts: every agent that touches
email ends up holding a copy of every mailbox password, on its own server, in
its own config. mailgrant puts one gateway in front of the mailboxes instead.
You register each mailbox **once**, then decide who may use which mailboxes and
which actions:

- **Agents** get a bearer token and talk [MCP](https://modelcontextprotocol.io) (Streamable HTTP) or plain REST.
- **You** get an optional webmail app on your phone and computer, signed in with a passkey, with push notifications and a timeline of everything each agent did.

Every call from either side goes through the same grants and the same audit log.

<p align="center"><img alt="Agents and you on one side, the gateway in the middle, your mailboxes on the other" src="docs/assets/how-it-works.png" width="1280"></p>

## Contents

[In practice](#in-practice) · [Features](#features) · [Quick start](#quick-start) · [Connect an agent](#connect-an-agent) · [The web app](#the-web-app) · [Configuration](#configuration) · [REST API](#rest-api) · [Security](#security) · [FAQ](#faq)

## In practice

Once an agent is connected, you just ask. The agent only sees the tools and
mailboxes its token allows.

> **You:** What came in today on contact@ that still needs an answer?
>
> **Agent** calls `inbox(mailbox="contact", unseen=true, since="16-Oct-2026")`, then `get_message` on each:
>
> 3 unread. Mariana (clinic, 6 people) wants a quote for migrating their mailboxes.
> Pedro approved version 2 of the bakery site. A form notification says the October
> campaign link opens the wrong page. Want me to answer Mariana?

> **You:** Yes, reply in the same thread with our pricing, and mark the other two as read.
>
> **Agent** calls `send(mailbox="contact", to=["mariana@…"], in_reply_to="<…>", …)` and `mark_seen` twice.
> The reply lands in the mailbox's Sent folder, threaded, where your team (and the web app) can see it.

> **A read-only finance agent** tries `send(mailbox="billing", …)` and gets
> `403 scope`. It never saw a `send` tool in the first place, and the attempt
> shows up as **denied** in your audit log and in the app.

What people use it for:

| Case | Mailboxes | Scopes |
|---|---|---|
| **Customer support.** An agent answers the contact address inside the original thread, and the reply lands in Sent for the team to see. | `contact@` | `read`, `mark`, `send` |
| **Finance.** An agent reads invoices and receipts to reconcile payments. It can't reply or delete anything. | `billing@` | `read` |
| **Daily digest.** A scheduled script summarizes what arrived unread in every mailbox each morning. | `*` | `read` |
| **Personal assistant.** Triages your own inbox: marks what you've seen, trashes newsletters, answers the routine. | `you@` | `read`, `mark`, `delete`, `send` |
| **Agency with many clients.** Each client's agent reaches only that client's mailboxes, even on the same server. | `client-a@`, `billing@client-a` | `read`, `send` |
| **Lead intake.** A sales agent reads website form notifications and answers new leads from `sales@`, and sees nothing else. | `sales@` | `read`, `send` |

Rotating a mailbox password, cutting an agent off or adding a mailbox is a
change to the gateway. No agent has to be touched.

## Features

- **Per-agent grants**: mailboxes by name, address or `*` (including future ones); scopes `read`, `mark`, `delete`, `send`.
- **Invisible outside the grant**: a mailbox an agent can't use answers exactly like one that doesn't exist.
- **Scoped tool list**: MCP `tools/list` only shows the tools a token may call.
- **Unified inbox**: one call searches every granted mailbox in parallel.
- **Safe delete**: moves to the trash; erasing needs `permanent=true` and touches one message only.
- **Threaded replies** with `in_reply_to`, and a copy of every sent message in the Sent folder.
- **No spoofing**: `from_address` limited to the mailbox's own address and declared aliases.
- **Audit log**: metadata only, never subjects or bodies.
- **Reader mode** for agents: HTML mail comes back as clean text.
- **Optional webmail app**: installable PWA with passkeys, push, conversations, drafts, HTML mail in a sandbox, and the agents' activity. In English, Português, Español, Français and 简体中文.
- **Manage from the app (optional)**: add mailboxes, create agents, change their permissions and rotate tokens live, without a restart.
- **Stateless without the web app**: no database; connections open per request and close.
- **Secrets from the environment**: `${VAR}` anywhere, or the whole config in `MAILGRANT_CONFIG_B64`.

## Quick start

You need Docker and the IMAP/SMTP details of at least one mailbox (an app
password is best). Five minutes:

```bash
git clone https://github.com/lucasmaffei/mailgrant && cd mailgrant
cp config.example.yaml config.yaml

# 1. Mint a token per agent. Give the token to the agent; keep the hash.
docker run --rm ghcr.io/lucasmaffei/mailgrant:latest mailgrant token --name support-bot

# 2. Edit config.yaml: your mailboxes, the agents with their hashes,
#    and the `web:` section if you want the app (see below).

# 3. Validate it. It prints who may touch what.
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

The smallest useful `config.yaml`:

```yaml
agents:
  - name: support-bot
    token_sha256: "9f86d08…"          # printed by `mailgrant token`
    mailboxes: [contact]
    scopes: [read, mark, send]

mailboxes:
  - name: contact
    imap: {host: mail.example.com, username: contact@example.com, password: "${CONTACT_PASSWORD}"}
    smtp: {host: mail.example.com, username: contact@example.com, password: "${CONTACT_PASSWORD}",
           from_address: "Example <contact@example.com>", save_copy_to: Sent}
```

Deploying on a PaaS? There is a step-by-step guide for
**[Coolify](docs/deploy-coolify.md)**; the same environment variables work on
any Docker host. No registry access? `docker compose up -d --build` builds
from the checkout.

## Connect an agent

Any MCP client that supports Streamable HTTP with a bearer header works.
Full walkthrough, including Cursor and Claude Desktop: **[docs/connect-agents.md](docs/connect-agents.md)**.

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

### MCP tools

| Scope | Tools |
|---|---|
| — | `whoami` |
| `read` | `mailboxes`, `inbox`, `list_folders`, `list_messages`, `search`, `get_message` |
| `mark` | `mark_seen` |
| `delete` | `delete_message` |
| `send` | `send` |

Reading never changes a message: folders are opened read-only (`EXAMINE`), so
the Seen flag stays as the humans left it.

## The web app

<p align="center"><img alt="Inbox, conversation, writing and agent activity on a phone" src="docs/assets/screens.png" width="1280"></p>

A webmail for the person who owns the mailboxes, built into the same server.
It is **off by default**; add a `web:` section to turn it on:

```yaml
web:
  origin: https://mail.example.com     # where you open it
  data_dir: /data                       # SQLite for passkeys, push devices, history
  user: {name: you, mailboxes: ["*"], scopes: [read, mark, delete, send]}
```

Create your first passkey with `mailgrant invite` (a one-time link to open on
your phone) or by setting `MAILGRANT_SETUP_CODE` and typing it on the sign-in
screen. Then add the app to the Home Screen and turn notifications on.

- **A real mail client**: one inbox for every mailbox, conversations, reply all,
  forward, Cc/Bcc, attachments, drafts saved to the mailbox's Drafts folder,
  signatures, stars, archive, a Sent view that says who sent what, batch
  actions and swipe gestures on the phone.
- **HTML mail as designed**, sanitized and shown in a sandboxed frame; remote
  images wait until you allow them, per message or per sender.
- **Agent timeline**: what each agent read, sent or was denied, and when, with
  a push notification when an agent sends mail.
- **Manage everything from it** (`manage: true`): mailboxes, agents, scopes and
  tokens, live, with the passkey asked again for every change.
- **Five languages**: English, Português, Español, Français and 简体中文,
  picked from the device or chosen in Settings.
- The person is granted like an agent, so a read-only phone is one line.
  Remove the section and `/app` disappears; agents are not affected.

<p align="center"><img alt="The web app on a computer" src="docs/assets/desktop.png" width="1100"></p>

Full guide: **[docs/web-app.md](docs/web-app.md)** (install on iPhone,
notifications, what is stored, security model, turning it off).

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

web:                                  # optional, see "The web app"
  origin: https://mail.example.com
  data_dir: /data
  user: {name: owner, mailboxes: ["*"], scopes: [read, mark, delete, send]}
```

[`config.example.yaml`](config.example.yaml) documents every option.

### Rules worth knowing

- Grants are checked at startup: a typo in an agent's `mailboxes` stops the server instead of silently granting nothing.
- The same token (or hash) on two agents is an error.
- `token_sha256` keeps the file free of usable secrets; `token: "${VAR}"` keeps it in the environment. Both work.
- `auth.tokens` (from docker-mailbox) still works and grants everything to everyone holding it. `mailgrant check` warns about it.
- Changing the config file needs a restart. With `web.manage: true`, mailboxes and agents live in the app instead and change without one.

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

```bash
# Unread mail in every mailbox this token can read
curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8000/inbox?unseen=true&limit=20"

# Reply inside a thread
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/mailboxes/contact/send -d '{
    "to": ["client@example.com"], "subject": "Re: Order 42",
    "body_text": "It ships tomorrow.", "in_reply_to": "<original-message-id@example.com>"
  }'
```

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
- **The web app** signs in with passkeys only, keeps sessions in `HttpOnly`/`SameSite=Strict` cookies, checks `Origin` on every change, serves a CSP that loads nothing from other origins, and shows HTML mail sanitized in a sandboxed frame where no script can run. Details in [docs/web-app.md](docs/web-app.md#security-model).
- **A token is only as narrow as its grant.** Give agents the fewest mailboxes and scopes that do the job; reserve `"*"` for agents you'd trust with all of them.

Found a vulnerability? Please follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## FAQ

**Does it work with Gmail, Outlook, Fastmail, iCloud, Zoho, Mailcow…?**
Anything that speaks IMAP and SMTP. For Gmail, iCloud and Yahoo use an app
password; for self-hosted servers (Mailcow, Mailu, Dovecot/Postfix) a
dedicated app password per gateway is ideal.

**Is it an email server?** No. It never receives mail from the internet; it
logs in to your existing mailboxes like a mail client would.

**Do my emails pass through a third party?** No. You run it; mail goes from
your mail server to your gateway to your agent. Without the web app nothing is
stored at all; with it, passkeys, push subscriptions and an activity history
without subjects or bodies (and, with `manage: true`, the mailboxes and agents,
passwords encrypted).

**Which agents can use it?** Any MCP client with Streamable HTTP (Claude Code,
Codex, Cursor, Claude Desktop via `mcp-remote`, OpenClaw, Hermes…) and anything
that can make an HTTP request.

**Can an agent read everything?** Only what its grant says. A mailbox outside
the grant looks like it doesn't exist, and tools outside its scopes don't show
up.

## Running from source

```bash
uv sync --all-groups
uv run mailgrant check --config config.yaml
uv run mailgrant http --config config.yaml   # binds 127.0.0.1:8000
uv run pytest -q
```

The README art and screenshots are generated from [`docs/assets/src`](docs/assets/src).
Contributions are welcome, including new languages for the web app: see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

mailgrant is a fork of [docker-mailbox](https://github.com/psyb0t/docker-mailbox)
by Ciprian Mandache (psyb0t), which provides the IMAP/SMTP layer, the unified
inbox, reader mode and the MCP transport. mailgrant adds per-agent grants,
auditing, safe deletion, threaded sending and the web app.

## License

MIT, see [LICENSE](LICENSE). The Docker image bundles third-party components
under their own licenses (html2text is GPL-3.0; the web app's fonts are OFL);
see [THIRD_PARTY.md](THIRD_PARTY.md).
