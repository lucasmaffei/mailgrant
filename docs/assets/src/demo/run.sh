#!/bin/bash
# Screenshots for every language: bash run.sh [lang ...]  (default: all five)
# Needs Docker, uv and node with playwright. Uses its own Dovecot on 31144
# and mailgrant on 18200, and throws both away at the end.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../../.." && pwd)
WORK=$(mktemp -d)
LANGS=${*:-en pt-BR es fr zh-CN}
cleanup() { pkill -f "mailgrant http --config $WORK/" 2>/dev/null; pkill -f "aiosmtpd -n -l 127.0.0.1:2526" 2>/dev/null; docker rm -f mg-demo-dovecot >/dev/null 2>&1; }
trap 'cleanup; rm -f "$HERE/content.json"' EXIT

(cd "$HERE" && python3 -c "import json; from content import CONTENT; json.dump({'CONTENT': CONTENT}, open('content.json', 'w'), ensure_ascii=False)")
printf 'auth_allow_cleartext = yes\n' > "$WORK/test.conf"
docker rm -f mg-demo-dovecot >/dev/null 2>&1 || true
docker run -d --name mg-demo-dovecot -e USER_PASSWORD=pass -v "$WORK/test.conf:/etc/dovecot/conf.d/test.conf:ro" \
  -p 127.0.0.1:31144:31143 dovecot/dovecot:latest >/dev/null
sleep 5
# Sent mail goes nowhere: a local SMTP sink.
(cd "$WORK" && nohup uvx --from aiosmtpd==1.4.6 python -m aiosmtpd -n -l 127.0.0.1:2526 > smtp.log 2>&1 &)

for lang in $LANGS; do
  read -r CONTACT BILLING ME < <(cd "$HERE" && python3 -c "from content import CONTENT as C; b=C['$lang']['boxes']; print(b['contact'], b['billing'], b['me'])")
  mkdir -p "$WORK/$lang"
  cat > "$WORK/$lang/config.yaml" <<YAML
agents:
  - {name: hermes, token: "hermes-e2e", mailboxes: ["*"], scopes: [read, mark, send]}
web:
  origin: http://localhost:18200
  data_dir: $WORK/$lang/data
  poll_seconds: 3600
  user: {name: you, mailboxes: ["*"], scopes: [read, mark, delete, send]}
mailboxes:
YAML
  for pair in "contact $CONTACT" "billing $BILLING" "me $ME"; do
    set -- $pair
    cat >> "$WORK/$lang/config.yaml" <<YAML
  - name: $1
    imap: {host: 127.0.0.1, port: 31144, tls: none, username: "$2", password: pass}
    smtp: {host: 127.0.0.1, port: 2526, tls: none, username: "", password: "", from_address: "$2", save_copy_to: Sent}
YAML
  done
  (cd "$HERE" && python3 seed.py "$lang")
  (cd "$REPO" && uv run mailgrant http --config "$WORK/$lang/config.yaml" --port 18200 > "$WORK/$lang/server.log" 2>&1) &
  SERVER=$!
  for i in $(seq 1 40); do curl -sf http://localhost:18200/health >/dev/null && break; sleep 0.5; done
  (cd "$REPO" && uv run python "$HERE/agent.py" "$lang")
  (cd "$REPO" && uv run mailgrant invite --config "$WORK/$lang/config.yaml" | tail -1 | tr -d ' ') > "$WORK/$lang/invite.txt"
  (cd "$HERE" && node e2e.mjs "$lang" "$WORK/$lang/invite.txt" "$HERE/../shots/$lang")
  pkill -f "mailgrant http --config $WORK/$lang/" || true; wait $SERVER 2>/dev/null || true
done
echo "shots in docs/assets/src/shots/<lang>; now: node ../render.mjs"
