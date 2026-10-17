# Connecting agents to mailgrant

Every agent needs two things: the MCP URL (`https://<your-host>/mcp`) and **its
own token**. Don't share tokens between agents — the token is what decides
which mailboxes and actions an agent gets, and what the audit log calls it.

Mint tokens on the gateway side (`mailgrant token --name <agent>`, see
[deploy-coolify.md](deploy-coolify.md)). Below, `$MAILGRANT_TOKEN` is that
agent's token.

## Claude Code

```bash
claude mcp add --transport http mailgrant https://mail-mcp.example.com/mcp \
  --header "Authorization: Bearer $MAILGRANT_TOKEN"
```

Add `--scope user` to make it available in every project, or `--scope project`
to share it through `.mcp.json` (then reference the token from an env var
instead of pasting it). Check it with `claude mcp get mailgrant` — it should
say `✔ Connected`.

## Codex

```bash
export MAILGRANT_TOKEN=...      # in the environment Codex runs in
codex mcp add mailgrant --url https://mail-mcp.example.com/mcp \
  --bearer-token-env-var MAILGRANT_TOKEN
```

That writes to `~/.codex/config.toml`:

```toml
[mcp_servers.mailgrant]
url = "https://mail-mcp.example.com/mcp"
bearer_token_env_var = "MAILGRANT_TOKEN"
```

## Cursor and other clients with remote MCP

Most clients that accept a remote server take a URL and headers:

```json
{
  "mcpServers": {
    "mailgrant": {
      "url": "https://mail-mcp.example.com/mcp",
      "headers": { "Authorization": "Bearer <token>" }
    }
  }
}
```

## OpenClaw, Claude Desktop and stdio-only clients

Clients that only launch local processes use
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote) as a bridge:

```json
{
  "mcpServers": {
    "mailgrant": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote@0.1.38",
        "https://mail-mcp.example.com/mcp",
        "--transport", "http-only",
        "--header", "Authorization:${AUTH_HEADER}"
      ],
      "env": { "AUTH_HEADER": "Bearer <token>" }
    }
  }
}
```

The header goes through an env var because some clients split arguments on
spaces. For a plain-HTTP URL (local testing only) add `"--allow-http"`.

The repository also ships an OpenClaw plugin with the same bridge in
[`.agents/plugins/mailgrant`](../.agents/plugins/mailgrant).

## Teach the agent how to use it

Tools alone don't tell an agent the house rules: check `whoami` first, never
mark mail as read unless triaging, reply with `in_reply_to`, confirm before
deleting. Those live in the skill:
[`.agents/skills/mailgrant/SKILL.md`](../.agents/skills/mailgrant/SKILL.md).

- **Claude Code**: copy the folder to `~/.claude/skills/mailgrant/` (all
  projects) or `.claude/skills/mailgrant/` (one project).
- **Other agents**: put the file wherever the agent reads skills, or paste its
  body into the agent's instructions (`AGENTS.md`, system prompt).

## Without MCP: REST

Scripts, cron jobs and agents without MCP use the same token over REST:

```bash
H="Authorization: Bearer $MAILGRANT_TOKEN"
U=https://mail-mcp.example.com

curl -s -H "$H" $U/whoami
curl -s -H "$H" "$U/inbox?unseen=true&limit=20"
curl -s -H "$H" "$U/mailboxes/contact/messages/42?reader=true"
```

```python
import httpx

mail = httpx.Client(
    base_url="https://mail-mcp.example.com",
    headers={"Authorization": f"Bearer {token}"},
)
unread = mail.get("/inbox", params={"unseen": True}).json()["messages"]
for m in unread:
    full = mail.get(f"/mailboxes/{m['mailbox']}/messages/{m['uid']}", params={"reader": True}).json()
    print(m["mailbox"], m["subject"], full["body_reader"][:200])
```

## Let the agent set itself up

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

## First conversation

Once connected, ask the agent:

> Which mailboxes can you use through mailgrant, and what can you do with them?

It should call `whoami` and answer with exactly its grant. Then:

> Show me the unread email from the last two days.

That's `inbox` with `unseen` and `since`. If the agent tries a tool it doesn't
have, it gets a clear "lacks the 'x' scope" error, and the attempt shows up in
the audit log as `denied`.
