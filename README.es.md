<p align="center"><img alt="logo de mailgrant" src="src/mailgrant/web/static/icons/icon-192.png" width="88"></p>

<h1 align="center">mailgrant</h1>

<p align="center"><b>El gateway de correo autoalojado para agentes de IA.</b><br>
Cada agente recibe su propio token, sus propios buzones y sus propios permisos. Las contraseñas de los buzones se quedan contigo.</p>

<p align="center">
  <a href="https://github.com/lucasmaffei/mailgrant/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/lucasmaffei/mailgrant/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="MCP: Streamable HTTP" src="https://img.shields.io/badge/MCP-Streamable%20HTTP-38cfff?labelColor=05090b">
  <img alt="Imagen Docker en GHCR" src="https://img.shields.io/badge/docker-ghcr.io%2Flucasmaffei%2Fmailgrant-0b1114?logo=docker&logoColor=white&labelColor=05090b">
  <a href="LICENSE"><img alt="Licencia: MIT" src="https://img.shields.io/badge/license-MIT-0b1114?labelColor=05090b"></a>
</p>

<p align="center"><a href="README.md">English</a> · <a href="README.pt-BR.md">Português</a> · <b>Español</b> · <a href="README.fr.md">Français</a> · <a href="README.zh-CN.md">简体中文</a></p>

<p align="center"><img alt="mailgrant: un solo gateway de correo para personas y agentes de IA, cada uno con sus propios buzones y permisos" src="docs/assets/hero.es.png" width="1280"></p>

Sin un gateway, todo agente que toca el correo (Claude, Codex, OpenClaw,
tus propios scripts) guarda una copia de la contraseña de cada buzón. Con
mailgrant registras cada buzón **una sola vez**, y cada agente recibe un token
que abre solo los buzones y las acciones que elegiste. Los agentes hablan
[MCP](https://modelcontextprotocol.io) o REST, y cada llamada se verifica y
queda registrada.

<p align="center"><img alt="Los agentes y tú de un lado, el gateway en el medio, tus buzones del otro" src="docs/assets/how-it-works.es.png" width="1280"></p>

**Instalación:** [1. Obténlo](#1-obténlo) · [2. Configura](#2-configura) · [3. Ejecuta](#3-ejecuta) · [4. Conecta un agente](#4-conecta-un-agente)<br>
**Uso:** [El día a día](#el-día-a-día) · [La app web](#la-app-web-opcional) · [Documentación](#documentación)

## 1. Obténlo

Necesitas una máquina con Docker y los datos IMAP/SMTP de al menos un
buzón (lo ideal es una contraseña de aplicación).

```bash
git clone https://github.com/lucasmaffei/mailgrant && cd mailgrant
cp config.example.yaml config.yaml
```

## 2. Configura

La configuración tiene dos listas: **mailboxes** (los buzones a los que llega
el gateway) y **agents** (quién puede usar cada buzón, y para qué).

**Crea un token para tu primer agente:**

```bash
docker compose run --rm mailgrant mailgrant token --name support-bot
```

Imprime el token, que le das al agente, y su hash, que va en la
configuración. El token se muestra una sola vez y no se guarda en ningún lado.

**Reemplaza el contenido de `config.yaml` con tu buzón y ese agente:**

```yaml
mailboxes:
  - name: contact
    imap: {host: mail.example.com, username: contact@example.com, password: "${CONTACT_PASSWORD}"}
    smtp: {host: mail.example.com, username: contact@example.com, password: "${CONTACT_PASSWORD}",
           from_address: "Example <contact@example.com>", save_copy_to: Sent}

agents:
  - name: support-bot
    token_sha256: "9f86d08…"          # el hash impreso arriba
    mailboxes: [contact]              # nombres, direcciones o "*" para todos
    scopes: [read, mark, send]        # read · mark · delete · send
```

**Pon la contraseña en un archivo `.env`** al lado, así la configuración no
guarda ningún secreto:

```bash
echo 'CONTACT_PASSWORD=la-contraseña-del-buzón' > .env
```

**Valida la configuración.** Muestra quién puede tocar qué, o exactamente qué está mal:

```bash
docker compose run --rm mailgrant mailgrant check
```

```text
ok: 1 mailbox(es), 1 agent(s)
  support-bot          [mark, read, send]  contact
web app: off (no `web:` section)
```

Puertos, TLS, alias, la carpeta de papelera y todas las demás opciones:
[docs/configuration.md](docs/configuration.md).

## 3. Ejecuta

```bash
docker compose up -d
curl -s http://127.0.0.1:8000/health      # {"ok":true,"version":"…"}
```

El puerto solo escucha en `127.0.0.1`. Para agentes en otras máquinas, ponlo
detrás de HTTPS con un proxy inverso (Caddy, Traefik, nginx) o una plataforma como
Coolify ([paso a paso](docs/deploy-coolify.md)).

## 4. Conecta un agente

El agente necesita la dirección `https://<your-host>/mcp` y su token:

```bash
# Claude Code
claude mcp add --transport http mailgrant https://mail-mcp.example.com/mcp \
  --header "Authorization: Bearer $MAILGRANT_TOKEN"

# Codex
codex mcp add mailgrant --url https://mail-mcp.example.com/mcp \
  --bearer-token-env-var MAILGRANT_TOKEN
```

Luego pregúntale *"¿Qué buzones puedes usar a través de mailgrant?"*. Debería
responder exactamente con lo que le concediste.

Cursor, Claude Desktop, OpenClaw, REST puro y un prompt para que el
agente se configure solo: [docs/connect-agents.md](docs/connect-agents.md).

## El día a día

Edita `config.yaml` o `.env` y aplica el cambio con
`docker compose up -d --force-recreate` (un `restart` simple no vuelve a leer
`.env`). Los agentes conservan sus tokens y no necesitan ningún cambio.

| Para… | Haz esto |
|---|---|
| **Agregar un buzón** | Agrégalo en `mailboxes` y su contraseña en `.env`. Los agentes con `"*"` lo reciben de inmediato; los demás lo necesitan en sus `mailboxes`. |
| **Agregar un agente** | Ejecuta `mailgrant token --name <agent>`, agrega una entrada en `agents` con el hash y dale al agente su token. |
| **Cambiar lo que puede hacer un agente** | Edita sus `mailboxes` y `scopes`. |
| **Cortarle el acceso a un agente** | Quita su entrada. Su token deja de funcionar al instante. |
| **Cambiar la contraseña de un buzón** | Cámbiala en `.env`. Los agentes nunca la conocieron. |
| **Ver qué hicieron los agentes** | `docker compose logs mailgrant \| grep mailgrant.audit` da una línea JSON por llamada, sin asuntos ni cuerpos. |
| **Actualizar mailgrant** | `git pull && docker compose up -d --build` |

¿Prefieres hacer clic? Con la app web y `manage: true`, agregas
buzones y agentes en la app, y los cambios se aplican sin reiniciar.

## La app web (opcional)

<p align="center"><img alt="Bandeja de entrada, conversación, redacción y actividad de los agentes en un celular" src="docs/assets/screens.es.png" width="1280"></p>

Un webmail para ti, integrado en el mismo servidor. Todos los buzones están en una
sola bandeja, el correo HTML se muestra de forma segura y puedes responder y adjuntar archivos. Recibes
notificaciones push en el celular, una línea de tiempo con lo que cada agente leyó y
envió, e inicio de sesión con passkey. Viene en English, Português, Español, Français
y 简体中文.

Viene desactivada por defecto. Para activarla, agrega esto a `config.yaml` y aplícalo de la misma forma:

```yaml
web:
  origin: https://mail.example.com      # la dirección HTTPS donde la abres
  user: {name: you, mailboxes: ["*"], scopes: [read, mark, delete, send]}
```

Luego ejecuta `docker compose exec mailgrant mailgrant invite` y abre en tu
celular el enlace que imprime para crear tu passkey.

Instalarla en el celular, notificaciones, administrar agentes desde la app:
[docs/web-app.md](docs/web-app.md).

## Documentación

Las guías están en inglés.

| | |
|---|---|
| [Qué hace](docs/overview.md) | Conversaciones de ejemplo, casos de uso, funcionalidades, preguntas frecuentes |
| [Configuración](docs/configuration.md) | Todas las opciones, reglas, variables de entorno, registro de auditoría |
| [Conectar agentes](docs/connect-agents.md) | Claude Code, Codex, Cursor, Claude Desktop, OpenClaw, REST |
| [Herramientas MCP y API REST](docs/api.md) | Herramientas por scope, rutas, parámetros, errores |
| [App web](docs/web-app.md) | Instalación, notificaciones, administración desde la app, qué se guarda |
| [Desplegar en Coolify](docs/deploy-coolify.md) | Paso a paso, con HTTPS y secretos en la plataforma |
| [Seguridad](docs/security.md) | Cómo el gateway protege los buzones y los tokens |

Las contribuciones son bienvenidas, incluidos nuevos idiomas para la app web: consulta
[CONTRIBUTING.md](CONTRIBUTING.md). ¿Encontraste una vulnerabilidad? Sigue
[SECURITY.md](SECURITY.md).

## Créditos y licencia

mailgrant es un fork de [docker-mailbox](https://github.com/psyb0t/docker-mailbox)
de Ciprian Mandache (psyb0t), que aporta la capa IMAP/SMTP, la bandeja
unificada, el modo lectura y el transporte MCP. mailgrant agrega permisos por agente,
auditoría, borrado seguro, envío en hilo y la app web.

MIT, ver [LICENSE](LICENSE). La imagen Docker incluye componentes de terceros
bajo sus propias licencias; ver [THIRD_PARTY.md](THIRD_PARTY.md).
