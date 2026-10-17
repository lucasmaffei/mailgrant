# Changelog

## Unreleased

- **The README is a guide to installing, configuring and running mailgrant**, in four steps and a day-to-day table, in all five languages. The reference moved to `docs/`: configuration (`configuration.md`), MCP tools and REST API (`api.md`), security (`security.md`), and examples, features and FAQ (`overview.md`). The prompt that lets an agent set itself up is now in `connect-agents.md`.
- Fix: `docker-compose.yml` now passes the variables in `.env` to the container. Before, a config that referred to `${CONTACT_PASSWORD}` stopped at start with "references unset environment variable" unless you added the variable to the compose file yourself.

## v0.12.1

- Fix: after an update the browser could pair the new JavaScript with the old stylesheet, and the new Settings came out broken (giant arrows, no columns). Static files now always revalidate (`cache-control: no-cache`), the page loads `app.css` and `app.js` with the version in the URL, and icons carry a size of their own so a missing stylesheet can't blow them up.

## v0.12.0 — Settings in sections

- **Settings is a list of sections**, each on its own page: Email mailboxes and Agents (with `manage`), Notifications, Reading, Signatures, Language, Passkeys and devices, About. On a phone the list opens each section with a back button; on a computer the list stays on the left and the section opens beside it. Each row says where things stand (how many mailboxes and agents, notifications on or off, the current language).
- Links go straight to a section (`#/settings/notifications`, `#/settings/language`…); after saving a mailbox or an agent the app returns to its section.
- **Download config** moved to About, next to the version and a link to the source.

## v0.11.0 — five languages, open source

- **The web app speaks English, Português (Brasil), Español, Français and 简体中文.** It follows the device's language until you pick one in Settings; the choice applies at once, on every device, and push notifications follow it. Dates, times and sizes use the language's own formats. Adding a language is one JSON file (see CONTRIBUTING.md).
- The API returns codes instead of Portuguese words for agent marks (`"what": "read" | "replied"`); the app words them.
- 12-hour clocks where the language uses them ("8:05 AM"), and the agent timeline no longer wraps the time.
- The README in five languages, with screenshots of the app in each; contributing guide, security policy, code of conduct and issue templates.

## v0.10.0 — HTML mail, shown properly

- **HTML mail is shown as it was designed** instead of flattened to text, where receipts and newsletters built from layout tables came out as rows of `| | |`. The body is sanitized on the server (nh3), served as its own document with a CSP that allows no script at all and a CSP sandbox, and drawn in a sandboxed iframe that grows to its content and scales 600px layouts down to the phone's width.
- **Remote images are held back** until you tap **Mostrar**, or **Sempre de <domínio>** for a sender; Ajustes has a switch for all senders and a way to forget the allowed ones. Held-back images keep their space without the broken-image icon. Inline (`cid:`) images always show.
- The text agents get from HTML mail (and the app's snippets) no longer carries table markup.
- Fix: two processes opening a new data directory at the same moment could both try to add the 0.9 `confirmed_at` column, and the second one failed to start.

## v0.9.1

- **Enviados**: what went out of every mailbox's Sent folder, with who sent it (you, or which agent, from the audit log). Opening a sent message shows the conversation, replies from the inbox included.
- A side menu on phones (the button at the top of the list, Agentes and Ajustes), the same as the computer's sidebar.
- Mailbox tabs and the sidebar show whole addresses; long ones wrap instead of being cut.
- Fix: replying in a conversation of three or more messages failed. The References header comes folded over several lines and was passed along with the line breaks, which the header-injection check refuses; ids are now read on one line.
- Fix: the tap that ends a long press no longer toggles the row that lands under the finger after the list redraws.

## v0.9.0 — manage mailboxes and agents in the app

- **`web.manage: true`** moves mailboxes and agents into the web app's database. The first start imports them from the config; after that the file's `mailboxes` and `agents` are ignored and every change in **Ajustes** applies at once on every worker, without a restart (each request checks a config version, at most once a second).
- Add, edit and remove mailboxes, with **Testar conexão** (IMAP login and folder list, SMTP login). Passwords are encrypted at rest with `MAILGRANT_SECRET_KEY` (or a key file in `data_dir`), never sent back to the browser, and kept when a form leaves them blank.
- Create agents, choose their mailboxes (or all, including future ones) and scopes, issue a new token (shown once, with a ready MCP configuration), remove them. Only token hashes are stored.
- Every change needs a passkey check from the last five minutes; the app asks for Face ID / Touch ID again.
- **Baixar config** exports the current config as YAML, passwords included.
- With `manage` on, every MCP tool is registered up front, since mailboxes can appear while running.
- `mailgrant check` says when `manage` is on.

## v0.8.0 — a fuller mail client

The web app grew the basics a mail client is expected to have. Agents, MCP and REST are unchanged.

- **Conversations.** The inbox groups messages by thread (Message-ID, In-Reply-To and References, so a reply that only names its parent still joins), and opening one shows the whole conversation, including your own messages from Sent, with older ones folded. Can be turned off in Ajustes.
- **Writing.** Reply all (your own addresses left out), forward with the original attachments, Cc and Bcc, attach files from the device (25 MB per message), a signature per mailbox.
- **Drafts** are saved to the mailbox's Drafts folder while you type and listed under Rascunhos; sending one removes it. Saving replaces the previous version, and only messages flagged `\Draft` can be erased that way.
- **Organizing.** Stars and a Com estrela view, archive (creates "Archive" when the mailbox has none), read/unread and trash on one message, a whole conversation or a selection. On phones: swipe right for read/unread, left to archive, hold to select.
- "Carregar mais antigas" pages back through the inbox.
- Fixes: recipients with a display name ("Recepção <r@x>") went to SMTP with the name and failed on servers without SMTPUTF8; the envelope now carries bare addresses. A slow list response could replace a newer one when switching views quickly.

## v0.7.1

- **Setup code.** `MAILGRANT_SETUP_CODE` (or `web.setup_code`) lets the first passkey be created by typing the code on the sign-in screen, without opening a terminal for `mailgrant invite`. It only works while no passkey exists, and is checked again when the passkey is saved.
- Invite tokens are hex. URL-safe tokens could end in `_` or `-`, which terminals and chat apps drop when they turn the URL into a link, and the invite then looked "used or expired".
- Sign-up errors in the app are in Portuguese and say whether the invite or the code was wrong.

## v0.7.0 — the web app

- **Optional web app** at `/app`, turned on by a `web:` section: unified inbox with mailbox filter and search, message reading (HTML shown as text), reply in thread and compose, mark read/unread, move to trash, attachments download, agent activity timeline, settings. Responsive: one column on phones, three on desktops. Interface in Brazilian Portuguese.
- **Passkeys only** (WebAuthn, user verification required). The first device registers through a one-time invite from `mailgrant invite`; more devices from Settings. Sessions in `HttpOnly`/`Secure`/`SameSite=Strict` cookies, `X-Mailgrant` header and `Origin` check on every change.
- **Installable PWA** with Web Push (VAPID, generated on first use): per-mailbox notification choice, optional push when an agent sends mail, unread badge on the app icon. New mail is detected by polling `STATUS` every `poll_seconds`; only one worker watches.
- The signed-in person is granted by `web.user` exactly like an agent, and goes through the same checks and audit log.
- When the web app is on, the audit log is also kept in SQLite (180 days, metadata only) for the Agents screen and the "hermes leu" / "hermes respondeu" marks.
- Strict CSP (self only, fonts bundled), security headers, attachments always served as downloads.
- Without a `web:` section nothing changes: no routes, no database, the web modules aren't loaded.
- `mailgrant check` reports whether the web app is on. Compose gains a `/data` volume.
- Send audits record `in_reply_to`. Message results include `references` and attachment `index`.
- README and docs redone in the web app's look, with real screenshots; guide in `docs/web-app.md`.

## v0.6.1

- `MAILGRANT_CONFIG_B64`: the whole config as one base64 line. Coolify writes environment variables to a dotenv file, and a multi-line `MAILGRANT_CONFIG_YAML` broke the deploy. The Coolify guide now uses it.

## v0.6.0 — mailgrant

First release as **mailgrant**, a fork of [docker-mailbox](https://github.com/psyb0t/docker-mailbox) v0.5.1.

- **Per-agent grants.** `agents` in the config give each bearer token its own mailboxes (names, addresses or `*`) and scopes (`read`, `mark`, `delete`, `send`). Mailboxes outside a grant answer like unknown ones; missing scopes are 403 over REST and an error over MCP. `tools/list` only shows the tools a token may use. `auth.tokens` keeps working with full access.
- Tokens can be stored as `token_sha256`; `mailgrant token` mints one with its hash. Duplicate tokens or hashes are rejected.
- `whoami` (REST and MCP) tells an agent its own grant.
- Audit log: one JSON line per mail operation on `mailgrant.audit`, allowed or denied. No subjects or bodies.
- **Delete moves to the trash** and returns `moved_to`; `permanent=true` erases. Expunge is always `UID EXPUNGE` for that one message — a bare `EXPUNGE` removed every `\Deleted` message in the folder, including ones flagged by other mail clients. Servers without UIDPLUS refuse permanent deletes instead.
- UIDs must be a single number. Ranges such as `1:*` were accepted and let one delete call wipe a folder.
- `send` takes `in_reply_to` and `references` to answer inside a thread, refuses a `from_address` other than the mailbox's own or `smtp.allowed_from`, and `smtp.save_copy_to` files a copy of every sent message over IMAP.
- Config: `${ENV_VAR}` references in any string, the whole file through `MAILGRANT_CONFIG_YAML`, unknown mailbox references in grants fail at startup. `mailgrant check` validates a config and prints the access matrix.
- Folder names with spaces (`"Caixa de entrada"`) are parsed correctly; capabilities are re-read after login (Dovecot only advertises MOVE/UIDPLUS then).
- Renamed package, CLI and env vars (`mailboxd` → `mailgrant`, `MAILBOXD_CONFIG` → `MAILGRANT_CONFIG`); Compose publishes on loopback by default; license is MIT.

The entries below are docker-mailbox's history.

## v0.5.1

- Clarify Docker's internal listener, the standalone CLI default, and host-side publishing. Documentation examples publish on host loopback and explain how to adjust the checked-in Compose file.

## v0.5.0

- Empty or omitted `auth.tokens` now denies protected HTTP and MCP requests instead of admitting anonymous access. `/health` remains public. Configure a bearer token and restart instances that previously ran without one.
- The standalone CLI now binds loopback by default. Set `--host 0.0.0.0` explicitly for network access. Container listeners remain available through published ports with bearer authentication.
- Pin PyJWT 2.15.1 to fix the reported dependency advisories. Dependency operations enforce a seven-day release-age cutoff.
- Close IMAP connections after login or TLS setup failures and report logout failures without logging credentials. Unified search no longer depends on a runtime assertion.
- Added HTTP, MCP, and real-network regression tests for authentication, mailbox selection, and credential forwarding. Configured tokens retain shared access to all mailboxes.
- Updated configuration examples, agent setup, and plugin metadata to require bearer credentials.
- Runtime version output now comes from installed package metadata.

## v0.4.16

Documentation only. The README's agent integrations section names [peen](https://github.com/psyb0t/peen) as an example of an agent that reads `.agents/skills/`.

## v0.4.15

Fixes the documented `/mcp` endpoint for Streamable HTTP clients that do not
follow redirects.

- `POST /mcp` returned `307` to `/mcp/` because the raw ASGI mount matched only
  the slash form. This broke MCP clients that retain the documented `/mcp` URL
  and do not follow redirects on Streamable HTTP requests.
- The app now normalizes only the exact `/mcp` path before routing. Bearer auth
  remains outermost, `/mcp/` still works, and the other HTTP routes keep their
  existing slash behavior.
- MCP contract tests now disable redirect following and cover both endpoint
  forms, so another redirect cannot pass unnoticed.
- Removed stale wording from the CI workflow comment. No behavior change.

## v0.4.14

Refreshes the MCP stack and locks the Python dependency graph.

- Upgraded the MCP SDK to 1.28.1 and Black to 26.3.1. Both runtime and
  development images now install strictly from `uv.lock`; they no longer fall
  back to an unlocked resolution.
- Added a Streamable HTTP MCP contract test that initializes the mounted route,
  lists the exposed tools, and calls `mailboxes` through the real application.
- Package commands now update exact pins correctly and support the `dev` group,
  so a development-only tool does not collide with runtime dependencies.
- Aligned Python runtime, package, health-response example, and Codex plugin
  version declarations with the release tag.

## v0.4.13

Fixes an IMAP command injection vulnerability (issue #1). Closes #1.

- The `folder`, `uid` and `search` values that reach the IMAP client were
  string-interpolated into IMAP commands and handed to Python's `imaplib`,
  which does not sanitize its own arguments. A CR/LF in any of them (reachable
  from an ordinary `%0D%0A` in an HTTP query or path parameter) ended the
  current command and spliced a second, attacker-chosen IMAP command onto the
  same authenticated connection, including a `STORE +FLAGS (\Deleted)` +
  `EXPUNGE` pair that deletes a whole folder through the read-only message
  routes.
- Every such value is now validated before it reaches `imaplib`: `folder`,
  `search` and structured search terms (including `since`/`before`) reject CR,
  LF and NUL; `uid` must be digits and sequence-set punctuation only; and
  folder names have any embedded `"` and `\` escaped so they cannot break out
  of the IMAP quoted string. The checks live in `imap_client`, so both the
  HTTP API and the MCP server inherit them.
- Added an in-process mock IMAP server and an IMAP test suite: the happy path
  (list, fetch, structured search) plus the injection cases, including the
  verbatim issue #1 payload driven through the read-only GET route.

## v0.4.12

Fixes the CI lint failure introduced by v0.4.11 so the image builds and publishes.

- v0.4.11 added `make lint` to CI for the first time, which surfaced a pre-existing flake8
  E501: a 103-character line in `src/mailboxd/server.py`. The lint job failed and the image
  build and publish steps, which depend on it, were skipped. Wrapped the line so flake8
  passes. No behavior change.

## v0.4.11

CI now lints, tests, and security-scans the code before building the image, via
the generic reusable code-workflow.

- New `code` pipeline job runs `make lint` (flake8 + mypy), `make test` (pytest
  unit + docker-in-docker integration), and `make sec`, and the image build now
  waits on it. The pipeline previously built and published the image without
  running any of these.
- New `make sec`: semgrep, bandit and pip-audit run in parallel and their
  findings merge into `sec.sarif` for the GitHub Security tab. It never fails the
  build; findings are reported, not gated. The scanners live in an isolated venv
  in the dev image so semgrep's bundled mcp pin cannot collide with the project's
  `mcp==1.9.0`.
- Removed the `make check` alias; use `make lint`, `make test`, `make sec`.
- Kept `.telemetry/` out of git and out of the image.

## v0.4.10

CI plumbing only. No code in this repo changed — every commit in this release touches `.github/workflows/`.

- The pipeline was split: building and publishing stay in `pipeline.yml`, and everything that leaves the host now lives beside it in `mirror-and-archive.yml`.
- The repo is mirrored to Codeberg as well as GitLab.
- It is archived to the Wayback Machine, Software Heritage and archive.org.
- Issues opened on either mirror are copied back to GitHub every six hours, and closed here when the original closes.
- Pull requests are switched off on the mirrors — they are force-pushed from GitHub, so anything merged there would be destroyed by the next sync. Issues and forking stay enabled.

## v0.4.9

Codex install command was missing from the README. Documentation only, no behavior change.

- The Codex subsection of `## Agent integrations` told readers to run `codex plugin marketplace add psyb0t/agents` and stopped there — it never showed the actual install command. Added `codex plugin add mailbox@psyb0t` right after it.
- Clarified that the invocation form depends on how the skill was obtained: installed via the marketplace it's `$mailbox:docker-mailbox`; picked up automatically (no install) from a repo's own `.agents/skills/` it's plain `$docker-mailbox`.

## v0.4.8

Renames the plugin from `docker-mailbox` to `mailbox`. Metadata only, no behavior change.

- **The install name is now `mailbox@psyb0t`.** v0.4.7 named the plugin after the repository, which made it the only entry in the `psyb0t` marketplace carrying a `docker-` prefix; every other plugin installs under its bare tool name. `mailbox` also matches the MCP-bridge plugin in `.agents/plugins/mailbox` and the container's own name.
- The ClawHub skill is unaffected and stays `@psyb0t/docker-mailbox`, as does `openclaw plugins install clawhub:@psyb0t/mailbox`. Only the Claude Code / Codex plugin identifier changed.

## v0.4.7

Agent-client distribution wiring. Documentation and metadata only, no behavior change.

- Added `.agents/.claude-plugin/plugin.json` and `.agents/.codex-plugin/plugin.json` so the existing `docker-mailbox` skill installs natively as a plugin in Claude Code and Codex, rooted at `.agents/`.
- New `## Agent integrations` README section (with Table of Contents entry) documenting the `claude plugin` / `codex plugin` marketplace install commands, the OpenClaw skill install, and the OpenClaw MCP-bridge plugin install for `@psyb0t/mailbox`.

## v0.4.6

- Added a GitHub Actions CI status badge to the README.

## v0.4.5

- Added self-hosted version and license badges plus a Docker Hub pulls badge; wired a badges job into pipeline.yml.

## v0.4.4

Listed on the official MCP Registry — no behavior change.

- Added `server.json` — published to the official Model Context Protocol Registry (`registry.modelcontextprotocol.io`) as `io.github.psyb0t/mailbox`, pointing at the `psyb0t/mailbox` Docker image. Ownership is proven by an `io.modelcontextprotocol.server.name` LABEL on the image; publishing runs on tag pushes via GitHub OIDC (secretless). Also added a `glama.json` maintainer claim.

## v0.4.3

Third-party license notices. Documentation only, no behavior change.

- Added `THIRD_PARTY.md` + `LICENSES/` documenting the GPL-3.0 `html2text` dependency bundled into the published image. The project's own code stays WTFPL.
- gitignore the container-generated `CLAUDE.md` so it never ships.

## v0.4.2

Skill docs de-duplicated. Documentation only, no behavior change.

- Collapsed the three repeated message-deletion warnings in `.agents/skills/docker-mailbox/SKILL.md` into one clear mention in the delete-endpoint reference plus a brief Security & safety note.

## v0.4.1

- Hardened the skill docs with explicit destructive-operation guardrails and auth/exfil warnings. No behavior change — documentation only.
  - New "Security & safety" section in the `docker-mailbox` skill.
  - `DELETE /mailboxes/<name>/messages/<uid>` is now flagged as destructive & irreversible everywhere it's documented, with explicit confirm-before-delete guidance for agents.
  - The "Find and delete" workflow now treats the search step as a dry-run: list and confirm matches with the user before deleting, instead of piping a broad search straight into bulk delete.
  - Documented the unauthenticated-when-`auth.tokens`-is-empty risk and that `MAILBOX_URL` traffic leaves the host.

## v0.4.0

- ClawHub plugin: new `@psyb0t/mailbox` code plugin (stdio↔HTTP MCP bridge via `mcp-remote` to `/mcp`), MIT-licensed.
- Pipeline switched to reusable `clawhub-publish.yml` (publishes skill + plugin).
