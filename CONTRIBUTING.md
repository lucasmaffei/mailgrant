# Contributing to mailgrant

Thanks for helping. Issues, fixes, docs and translations are all welcome.

## Before you start

- **Bugs**: open an issue with what you did, what you expected and what
  happened, plus the mailgrant version (`/health`) and your mail server
  (Gmail, Mailcow, Dovecot…). Never paste tokens, passwords or real mail.
- **Security problems**: don't open an issue. Follow [SECURITY.md](SECURITY.md).
- **Bigger changes**: open an issue first so we can agree on the shape before
  you write the code. mailgrant tries to stay small: one gateway, clear grants,
  nothing stored that doesn't have to be.

## Development

```bash
uv sync --all-groups
uv run pytest -q                       # unit tests + Docker-backed IMAP/SMTP tests
uv run black src tests && uv run isort src tests && uv run flake8 src tests
uv run mailgrant http --config config.yaml
```

CI runs exactly those checks. The web app is plain JavaScript and CSS under
`src/mailgrant/web/static/`, with no build step: edit and reload.

A few rules the code follows:

- Every mail operation goes through the grant checks and writes an audit line.
  New tools or routes need both, and a test that a token without the scope is refused.
- Nothing from a message is ever inserted as HTML in the app. HTML bodies only
  show in the sandboxed frame (`web/html_view.py`).
- Comments explain *why*, not *what*.

## Translating the web app

The app speaks English, Português (Brasil), Español, Français and 简体中文.
English is the source; every other language is one JSON file in
`src/mailgrant/web/static/i18n/`.

1. Copy an existing file to `src/mailgrant/web/static/i18n/<code>.json` (for
   example `de.json`) and translate the values. Keep `{placeholders}` as they are.
   Plural entries are objects keyed by [plural category](https://cldr.unicode.org/index/cldr-spec/plural-rules)
   (`one`, `other`, …).
2. Add the code and the language's own name to `LANGS` in `app.js`, to
   `LANGUAGES` and `MESSAGES` in `src/mailgrant/web/i18n.py` (push
   notifications) and to the service worker's `ASSETS` in `static/sw.js`. The
   full checklist is in [docs/web-app.md](docs/web-app.md#adding-a-language).
3. Run `uv run pytest tests/test_i18n.py`: it fails on missing or stale keys
   and mismatched placeholders.

Fixes to existing translations are just as welcome; native speakers know best.

## Pull requests

- One topic per pull request, with tests for behavior changes.
- Add a line to `CHANGELOG.md` under a new version heading if the change is user-visible.
- By contributing you agree that your work is released under the [MIT License](LICENSE).
