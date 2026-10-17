# MCP tools and REST API

Agents reach the gateway at `/mcp` (MCP, Streamable HTTP) or through the REST
routes below. Both use the same bearer token and the same grants. To connect a
client, see [connect-agents.md](connect-agents.md).

## MCP tools

| Scope | Tools |
|---|---|
| — | `whoami` |
| `read` | `mailboxes`, `inbox`, `list_folders`, `list_messages`, `search`, `get_message` |
| `mark` | `mark_seen` |
| `delete` | `delete_message` |
| `send` | `send` |

Reading never changes a message: folders are opened read-only (`EXAMINE`), so
the Seen flag stays as the humans left it.

Every tool takes a `mailbox` argument (name or address) where it applies;
`inbox` searches every granted mailbox at once.

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
