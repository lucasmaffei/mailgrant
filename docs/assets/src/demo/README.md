# Screenshots for the README

The phone and desktop screenshots in `../shots/` are real captures of the web
app, against a throwaway Dovecot with demo mailboxes and real agent activity.

1. Dovecot: `docker run -d --name mg-dovecot -e USER_PASSWORD=pass -p 127.0.0.1:31143:31143 dovecot/dovecot:latest`
   with a `conf.d` file containing `auth_allow_cleartext = yes` (local test only).
2. `python3 seed.py` fills `contato@`, `financeiro@` and `lucas@exemplo.com.br`.
3. Run mailgrant with a config whose `web.origin` is `http://localhost:18100`,
   an agent `hermes` (token `hermes-e2e`) and the three mailboxes on
   `127.0.0.1:31143`, then `python agent.py` to have the agent read, reply and
   get denied.
4. `mailgrant invite > invite.txt`, then `node e2e.mjs shots` (Playwright).
   It signs in with a virtual WebAuthn authenticator, walks every screen and
   fails on any console or CSP error.
5. Copy the shots to `../shots/` and run `node ../render.mjs`.
