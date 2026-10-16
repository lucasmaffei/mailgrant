# Security policy

mailgrant holds mailbox passwords and hands out tokens, so security reports
are taken seriously.

## Reporting a vulnerability

Please **don't open a public issue**. Report it privately through GitHub:
**Security → Report a vulnerability** on this repository
([direct link](https://github.com/lucasmaffei/mailgrant/security/advisories/new)).

Include what an attacker can do, the steps to reproduce, and the version you
tested (`/health` shows it). You'll get an answer within a few days, and a fix
and an advisory crediting you (unless you prefer otherwise) once it's resolved.

## Supported versions

Fixes go into the latest release. Run the latest `ghcr.io/lucasmaffei/mailgrant`
image or the `main` branch.

## Scope

In scope: the gateway (MCP, REST, grants, audit), the web app (sessions,
passkeys, the HTML mail sandbox, the management screens) and the Docker image.

Out of scope: problems that need an already-compromised server or config, a
token or passkey the attacker already holds, or a mail server outside
mailgrant's control.
