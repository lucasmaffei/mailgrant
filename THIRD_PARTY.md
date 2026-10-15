# Third-Party Components

This project's own source is MIT (see [`LICENSE`](LICENSE)). The published
Docker image (`ghcr.io/lucasmaffei/mailgrant`) additionally bundles the third-party
components below as runtime dependencies. Their licenses apply to those
components, not to this project's source.

| Component | Kind | License | Source | Where it lives | Note |
| --- | --- | --- | --- | --- | --- |
| [html2text](https://github.com/Alir3z4/html2text) | runtime dependency | GPL-3.0 | https://github.com/Alir3z4/html2text | Installed into the published Docker image's Python virtualenv (`pyproject.toml` dependency, imported by `src/mailgrant/imap_client.py`) | GPL — runtime dependency installed into the published Docker image; the image is a GPL combined work. Corresponding source at the URL above. Full license text: [`LICENSES/GPL-3.0.txt`](LICENSES/GPL-3.0.txt). |

## Web app

Used only when the `web:` section is configured.

| Component | Kind | License | Source | Note |
| --- | --- | --- | --- | --- |
| [py_webauthn](https://github.com/duo-labs/py_webauthn) | runtime dependency | BSD-3-Clause | https://github.com/duo-labs/py_webauthn | Passkey registration and sign-in. |
| [pywebpush](https://github.com/web-push-libs/pywebpush) | runtime dependency | MPL-2.0 | https://github.com/web-push-libs/pywebpush | Web Push delivery; used unmodified. |
| [cryptography](https://github.com/pyca/cryptography) | runtime dependency | Apache-2.0 OR BSD-3-Clause | https://github.com/pyca/cryptography | Encrypts mailbox passwords managed in the web app (Fernet). |
| [Inter](https://github.com/rsms/inter), [Inter Tight](https://github.com/rsms/inter) | bundled font | SIL OFL 1.1 | https://github.com/rsms/inter | `src/mailgrant/web/static/fonts/`, latin subset from Google Fonts. |
| [Geist Mono](https://github.com/vercel/geist-font) | bundled font | SIL OFL 1.1 | https://github.com/vercel/geist-font | `src/mailgrant/web/static/fonts/`, latin subset from Google Fonts. |
