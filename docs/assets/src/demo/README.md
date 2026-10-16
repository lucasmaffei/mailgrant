# Screenshots for the README

The phone and desktop screenshots in `../shots/<lang>/` are real captures of
the web app, one set per language, against a throwaway Dovecot with demo
mailboxes (`content.py`, written natively for each language) and real agent
activity (`agent.py` reads, replies and gets denied over MCP).

```bash
bash run.sh              # all five languages, or: bash run.sh en fr
node ../render.mjs       # hero, how-it-works, screens, desktop, social
```

`run.sh` needs Docker, `uv` and Node with Playwright. It starts its own Dovecot
(port 31144), an SMTP sink and mailgrant (port 18200), signs in with a virtual
WebAuthn authenticator, walks every screen with `e2e.mjs`, fails on any console
or CSP error, and removes everything when it ends.

`social.png` is the repository's social preview: upload it in the GitHub
repository settings (it can't be set through the API).
