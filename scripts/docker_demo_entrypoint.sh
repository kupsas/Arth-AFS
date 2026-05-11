#!/usr/bin/env bash
# Start FastAPI + Next.js together for the public demo image (single container).
set -euo pipefail

cd /app
export PYTHONUNBUFFERED=1
uvicorn api.main:app --host 0.0.0.0 --port 8000 &
UV_PID=$!

cd /app/dashboard
npm run start -- -H 0.0.0.0 -p 3000 &
WEB_PID=$!

_term() {
  kill "$UV_PID" "$WEB_PID" 2>/dev/null || true
}
trap _term SIGTERM SIGINT

# Exit when either child exits (so a crash tears the container down).
wait -n
STATUS=$?
_term
wait || true
exit "$STATUS"
