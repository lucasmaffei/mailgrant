# mailgrant-mcp

A stdio bridge from any MCP client to a self-hosted
[mailgrant](https://github.com/lucasmaffei/mailgrant) gateway.

mailgrant already serves Streamable-HTTP MCP at `/mcp`, and most clients
(Claude Code, Codex, Cursor) can talk to it directly — see the main README.
This package is for clients that only launch local stdio servers, such as
OpenClaw. It forwards everything to your mailgrant instance through
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote), authenticating with
the agent's bearer token.

## Configuration

| Env var | Required | Description |
|---|---|---|
| `MAILGRANT_URL` | yes | Base URL of your instance, e.g. `https://mail-mcp.example.com`. The bridge appends `/mcp`. |
| `MAILGRANT_TOKEN` | yes | This agent's token, as minted by `mailgrant token`. |

## What the agent gets

Only the tools its token's scopes allow, over only its mailboxes:

| Scope | Tools |
|---|---|
| (any) | `whoami` |
| `read` | `mailboxes`, `inbox`, `list_folders`, `list_messages`, `search`, `get_message` |
| `mark` | `mark_seen` |
| `delete` | `delete_message` (moves to trash; `permanent=true` erases) |
| `send` | `send` |

## Run it from a checkout

The package isn't on npm yet. From the repository:

```bash
cd .agents/plugins/mailgrant
npm install
MAILGRANT_URL=https://mail-mcp.example.com MAILGRANT_TOKEN=... node bin/cli.js
```

Or skip the package entirely and use `mcp-remote` directly:

```bash
npx -y mcp-remote@0.1.38 https://mail-mcp.example.com/mcp \
  --transport http-only --header "Authorization: Bearer $MAILGRANT_TOKEN"
```

## License

MIT
