# What mailgrant does

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
