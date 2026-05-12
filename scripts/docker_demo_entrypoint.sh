#!/usr/bin/env bash
# Start Caddy + FastAPI + Next.js for the public demo image (single container).
# Caddy (:3000) reverse-proxies /api/* → FastAPI (:8000), else → Next.js (:3001).
set -euo pipefail

cd /app
export PYTHONUNBUFFERED=1

caddy run --config /etc/caddy/Caddyfile --adapter caddyfile &
CADDY_PID=$!

# Fly.io snapshots listening sockets as soon as the Machine is "started". If
# Caddy is not accepting on internal_port yet, deploy warns that nothing
# listens on 0.0.0.0:3000. Wait until Caddy serves /fly-healthz (Next.js may
# still be booting).
for _ in $(seq 1 90); do
	if curl -sf "http://127.0.0.1:3000/fly-healthz" >/dev/null 2>&1; then
		break
	fi
	sleep 0.2
done

uvicorn api.main:app --host 127.0.0.1 --port 8000 &
UV_PID=$!

cd /app/dashboard
npm run start -- -H 127.0.0.1 -p 3001 &
WEB_PID=$!

_term() {
  kill "$CADDY_PID" "$UV_PID" "$WEB_PID" 2>/dev/null || true
}
trap _term SIGTERM SIGINT

# Exit when any child exits (so a crash tears the container down).
wait -n
STATUS=$?
_term
wait || true
exit "$STATUS"
