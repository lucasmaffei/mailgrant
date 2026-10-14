# Deploying mailgrant on Coolify

This walkthrough gets mailgrant running on [Coolify](https://coolify.io) behind
HTTPS, with every secret kept in Coolify's environment variables and nothing
sensitive in git.

You'll end with:

- `https://mail-mcp.example.com/health` answering `{"ok": true}`
- one token per agent, each limited to its own mailboxes and scopes
- the audit log in Coolify's logs tab

## 1. Prepare the config

Write the config locally. It references secrets as `${VARS}` and stores agent
tokens only as hashes, so the file itself holds nothing usable.

```bash
git clone https://github.com/lucasmaffei/mailgrant && cd mailgrant
uv sync   # or use the Docker image, see the README

# One token per agent. Save each token for the agent; keep the hash for the config.
uv run mailgrant token --name support-bot
uv run mailgrant token --name assistant
```

```yaml
# mailgrant.yaml — safe to keep in a private repo or password manager
audit_log: true

agents:
  - name: support-bot
    token_sha256: "<hash printed for support-bot>"
    mailboxes: [contact]
    scopes: [read, mark, send]
  - name: assistant
    token_sha256: "<hash printed for assistant>"
    mailboxes: ["*"]
    scopes: [read, mark, delete, send]

mailboxes:
  - name: contact
    imap: {host: mail.example.com, username: contact@example.com, password: "${CONTACT_PASSWORD}"}
    smtp:
      host: mail.example.com
      port: 465
      tls: ssl
      username: contact@example.com
      password: "${CONTACT_PASSWORD}"
      from_address: "Example <contact@example.com>"
      save_copy_to: Sent
```

Check it before deploying:

```bash
CONTACT_PASSWORD=x uv run mailgrant check --config mailgrant.yaml
```

> **Mail server first.** If your IMAP server only accepts app passwords (Gmail,
> iCloud, Zoho with 2FA), create one per mailbox. If it's your own server
> (Mailcow, Dovecot), a dedicated mailbox password is enough.

## 2. Create the application

In Coolify: **+ New → Application**, then choose one:

- **From the Git repository** (recommended while the repo is private): pick your
  GitHub App source, the `mailgrant` repository and branch `main`.
  Build pack: **Dockerfile**.
- **From the Docker image**: `ghcr.io/lucasmaffei/mailgrant:latest`. A private
  GHCR image needs the server logged in to `ghcr.io` (Coolify → Servers →
  your server → Docker registry credentials).

Then, in the application's **General** tab:

| Field | Value |
|---|---|
| Ports Exposes | `8000` |
| Domains | `https://mail-mcp.example.com` |

Coolify's proxy issues the TLS certificate and forwards to port 8000. Don't
publish the port on the host (leave "Ports Mappings" empty): the proxy is the
only way in.

## 3. Environment variables

In **Environment Variables**, add:

| Name | Value | Notes |
|---|---|---|
| `MAILGRANT_CONFIG_B64` | `base64 < mailgrant.yaml \| tr -d '\n'` | One line. Mark it as a secret and **literal**. |
| `CONTACT_PASSWORD` | the mailbox password | One variable per `${…}` in the config. Secret. |
| `WORKERS` | `1` | Optional. Uvicorn workers; one is plenty for a handful of agents. |

Why base64: Coolify writes environment variables to a dotenv file that Docker
Compose parses, and a multi-line YAML value breaks it (`unexpected character
in variable name`). One base64 line survives any platform.
`MAILGRANT_CONFIG_YAML` (plain YAML) also exists for platforms that pass
variables straight through.

Either variable takes precedence over a mounted file, so you never need a
volume. A `${VAR}` without a matching variable stops the container at startup
with the variable's name in the log.

> Prefer a file? Use **Storages → Add → File mount** at
> `/etc/mailgrant/config.yaml` with the YAML itself, and skip
> `MAILGRANT_CONFIG_B64`.

## 4. Health check

In **Health Checks**, enable it with path `/health` and port `8000`. It's the
only route that needs no token.

## 5. Deploy and verify

Deploy, then from your machine:

```bash
curl -s https://mail-mcp.example.com/health
# {"ok":true,"version":"0.6.0"}

curl -s -H "Authorization: Bearer $SUPPORT_BOT_TOKEN" https://mail-mcp.example.com/whoami
# {"agent":"support-bot","scopes":["mark","read","send"],"mailboxes":["contact"],"all_mailboxes":false}

curl -s -H "Authorization: Bearer $SUPPORT_BOT_TOKEN" "https://mail-mcp.example.com/inbox?limit=3"
```

A `401` means the token doesn't match any hash. An empty `messages` list with
something under `errors` means mailgrant reached the mail server but the
mailbox login failed: check that mailbox's password variable.

Now connect your agents: [connect-agents.md](connect-agents.md).

## Day-to-day operations

**Add a mailbox.** Add it under `mailboxes`, add its password variable, and
either list it in an agent's `mailboxes` or rely on agents with `"*"`.
Re-encode it into `MAILGRANT_CONFIG_B64` and **Restart**. No agent needs to change.

**Add an agent.** `mailgrant token --name <agent>`, add the entry with the
hash, re-encode the config into the variable, restart, give the token to the
agent.

**Revoke an agent.** Remove its entry (or change the hash) and restart. Its
token stops working immediately; no mailbox password changes.

**Rotate a mailbox password.** Change it on the mail server, update the
variable, restart. Agents never knew it.

**Read the audit log.** The application's **Logs** tab; filter by
`mailgrant.audit`. Each line is JSON:

```json
{"ts":"2026-10-14T22:01:08+00:00","agent":"support-bot","action":"send","outcome":"ok","mailbox":"contact","to":["client@example.com"],"message_id":"<…>"}
```

Ship them elsewhere if you need retention: Coolify's logs rotate.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Deploy fails with `failed to read …/.env: unexpected character` | A multi-line value in an environment variable. Use `MAILGRANT_CONFIG_B64`. |
| Container exits at start with `references unset environment variable` | A `${VAR}` in the config has no Coolify variable. |
| `agent '…' references unknown mailbox` at start | Typo in an agent's `mailboxes`, or the mailbox was removed. |
| `login failed` in `errors` | Wrong mailbox password, or the server wants an app password. |
| `server lacks UIDPLUS` on delete | Your IMAP server can't expunge a single message safely; mailgrant refuses rather than risk others. Moving to trash still works if the server supports MOVE. |
| `no trash folder` on delete | Set `imap.trash_folder`, or create the folder. |
| Agents get `404` for a mailbox you can see in the config | Not in that agent's grant. `mailgrant check` prints the matrix. |
