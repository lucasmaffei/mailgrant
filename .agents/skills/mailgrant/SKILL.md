---
name: mailgrant
description: "Read, search, triage, answer and file email through a mailgrant gateway (MCP or REST). Use when an agent has a mailgrant token and must work with shared mailboxes. The token decides which mailboxes and actions are available — call whoami first. Deleting and sending need explicit user confirmation."
compatibility: Requires a running mailgrant instance, MAILGRANT_URL and this agent's MAILGRANT_TOKEN.
metadata:
  author: Lucas Maffei
  homepage: https://github.com/lucasmaffei/mailgrant
---

# mailgrant

mailgrant is an email gateway shared by several agents. Your token was granted
**some** mailboxes and **some** scopes:

| Scope | What it allows |
|---|---|
| `read` | list mailboxes, unified inbox, folders, search, read messages |
| `mark` | set or clear the Seen flag |
| `delete` | move a message to the trash (or erase it with `permanent`) |
| `send` | send mail from a mailbox you were granted |

Anything outside your grant behaves as if it did not exist: an unknown mailbox
error does not mean the address is wrong, only that it isn't yours. Don't try
other spellings to get around it.

## Start every session with `whoami`

```json
{"agent": "support-bot", "scopes": ["read", "send"], "mailboxes": ["contato-lumahost"], "all_mailboxes": false}
```

Plan only what those scopes allow. If the user asks for something outside
them, say which scope or mailbox is missing — the operator grants it in the
mailgrant config; you can't.

## Reading

- `inbox` is the main view: newest-first across all your mailboxes, each item
  tagged with `mailbox` and `mailbox_address`. Filter with `from`, `subject`,
  `text`, `since` (IMAP date, e.g. `14-Oct-2026`), `unseen`, `folder`, and
  `mailbox` (CSV of names or addresses).
- `get_message` with `reader=true` returns `body_reader`: the HTML body as
  clean text. Prefer it over `body_html`.
- Reading never marks a message as read. Humans share these mailboxes; leave
  the Seen flag alone unless the user asked you to triage (`mark_seen`).
- UIDs are per mailbox **and** per folder. Always pass the same `mailbox` and
  `folder` you got the UID from.

## Answering

Reply in the same thread: pass the original `message_id` as `in_reply_to`.

```json
{"mailbox": "contato-lumahost", "to": ["cliente@example.com"],
 "subject": "Re: Pedido 42", "body_text": "...",
 "in_reply_to": "<abc123@example.com>"}
```

- `from_address` may only be the mailbox's own address or an alias the
  operator allowed; anything else is refused.
- If the result has `copy_saved_to`, the message is in the Sent folder for
  everyone to see. A `copy_error` means it was sent but not filed — tell the user.
- Never send without the user's go-ahead on the final text and recipients,
  unless they explicitly delegated that kind of message to you.

## Deleting

`delete_message` moves the message to the mailbox's trash and returns
`moved_to`. It is recoverable. `permanent=true` erases it and is required to
delete from the trash itself — only do that when the user asked for exactly
that message to be gone for good.

Only delete UIDs the user confirmed. Never bulk-delete straight from a search
result: list, show what matched, confirm, then delete one UID at a time (UID
ranges like `1:*` are rejected).

## Errors

| Error | Meaning |
|---|---|
| `unknown mailbox` | Not in your grant (or doesn't exist). |
| `lacks the 'x' scope` | Your token can't do that; ask the operator. |
| `from_address ... is not allowed` | Use the mailbox's own address. |
| `no trash folder ...` | Mailbox has no trash, or the message is already there; needs `permanent`. |
| `invalid uid` | Pass a single numeric UID. |
| HTTP 401 | Token missing, mistyped or revoked. |

## REST equivalents

Same rules, same token (`Authorization: Bearer $MAILGRANT_TOKEN`):

```bash
curl -s -H "Authorization: Bearer $MAILGRANT_TOKEN" "$MAILGRANT_URL/whoami"
curl -s -H "Authorization: Bearer $MAILGRANT_TOKEN" "$MAILGRANT_URL/inbox?unseen=true&limit=20"
curl -s -H "Authorization: Bearer $MAILGRANT_TOKEN" "$MAILGRANT_URL/mailboxes/contato-lumahost/messages/42?reader=true"
curl -s -X POST -H "Authorization: Bearer $MAILGRANT_TOKEN" -H 'Content-Type: application/json' \
  "$MAILGRANT_URL/mailboxes/contato-lumahost/send" \
  -d '{"to":["a@example.com"],"subject":"Re: hi","body_text":"...","in_reply_to":"<abc@example.com>"}'
curl -s -X DELETE -H "Authorization: Bearer $MAILGRANT_TOKEN" \
  "$MAILGRANT_URL/mailboxes/contato-lumahost/messages/42"
```
