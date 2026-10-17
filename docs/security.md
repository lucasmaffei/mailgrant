# Security notes

- **Run it behind TLS.** Tokens and mail travel through it. Compose binds `127.0.0.1` by default; expose it only through an HTTPS reverse proxy.
- **The config holds mailbox passwords.** Prefer `${VAR}` references or `MAILGRANT_CONFIG_B64` from your platform's secret store; never commit a filled-in `config.yaml`.
- **Tokens are compared in constant time**, and every candidate is compared on every request.
- **IMAP command injection** is blocked at the boundary: control characters in folder names are rejected, folder names are quoted, UIDs are digits only.
- **Delete never erases by surprise**: trash first, `UID EXPUNGE` for exactly one message, refusal on servers without UIDPLUS.
- **The web app** signs in with passkeys only, keeps sessions in `HttpOnly`/`SameSite=Strict` cookies, checks `Origin` on every change, serves a CSP that loads nothing from other origins, and shows HTML mail sanitized in a sandboxed frame where no script can run. Details in [web-app.md](web-app.md#security-model).
- **A token is only as narrow as its grant.** Give agents the fewest mailboxes and scopes that do the job; reserve `"*"` for agents you'd trust with all of them.

Found a vulnerability? Please follow [SECURITY.md](../SECURITY.md) instead of opening a public issue.
