# Public demo deployment (Fly.io / VPS)

This repo ships a **demo mode** that gives every browser its own disposable SQLite copy
of `data/arth_demo_seed.db` (see `api/demo.py` + `scripts/generate_demo_seed.py`).

## Environment variables

| Variable | Where | Purpose |
|----------|--------|---------|
| `ARTH_DEMO_MODE` | API | Set to `1` / `true` to enable per-session DB + demo routes. |
| `ARTH_DEMO_SEED_PATH` | API | Optional override; default `/app/data/arth_demo_seed.db` in Docker. |
| `ARTH_DEMO_CHAT_LIMIT` | API | Max Ask Arth user turns per browser session (default `15`). |
| `ARTH_DEMO_SESSION_TTL_HOURS` | API | Temp DB files older than this are deleted (default `4`). |
| `NEXT_PUBLIC_DEMO_MODE` | Web build | Set to `1` at **build time** for banner + settings view-only UI. |
| `NEXT_PUBLIC_WS_URL` | Web build | `wss://…` / `ws://…` to FastAPI when using `NEXT_PUBLIC_API_URL=same-origin`. |
| `OPENAI_API_KEY` / etc. | API | LLM keys for live Ask Arth in the demo (use a cheap model + low limits). |

## Option A — single image (`Dockerfile.demo`)

```bash
docker build -f Dockerfile.demo -t arth-demo .
docker run --rm -p 3000:3000 -p 8000:8000 \
  -e OPENAI_API_KEY=sk-... \
  arth-demo
```

Open `http://localhost:3000`.

## Option B — Compose (`docker-compose.demo.yml`)

Generate the seed once on the host (ignored by git, but required for the `:ro` mount):

```bash
python3 scripts/generate_demo_seed.py
docker compose -f docker-compose.demo.yml up --build
```

## Fly.io (outline)

1. Install the [Fly CLI](https://fly.io/docs/hands-on/install-flyctl/) and `fly auth login`.
2. Copy `fly.demo.toml` → `fly.toml`, set `app = "your-unique-name"`.
3. `fly secrets set OPENAI_API_KEY=...` (and any other LLM keys you need).
4. `fly deploy --dockerfile Dockerfile.demo`

Point `demo.yourdomain.com` at the Fly app; terminate TLS at Fly (default). Add the
HTTPS origin to `CORS_EXTRA_ORIGINS` on the API if the UI is on a different hostname.

## Cost hygiene

- Keep `ARTH_DEMO_CHAT_LIMIT` low; prefer a small / fast model for the playground.
- Demo session DBs live under `/tmp/arth_demo_sessions` inside the container unless
  `ARTH_DEMO_SESSION_DIR` overrides — size scales with concurrent visitors × DB size.
