# ⚡ HookPilot

**Self-hosted webhook inspector, debugger and replayer.**

Capture every webhook your services send, inspect headers and body in a live UI, replay requests to any URL, and get notified on Telegram — all in one Docker container with zero cloud dependencies.

---

## Why HookPilot?

| | HookPilot | RequestBin | Webhook.site | Hookdeck |
|---|---|---|---|---|
| Self-hosted | ✅ | ❌ | ❌ | ❌ |
| Persistent storage | ✅ | ❌ | limited | ✅ |
| Request replay | ✅ | ❌ | ❌ | ✅ |
| Auto-forward | ✅ | ❌ | ❌ | ✅ |
| Telegram alerts | ✅ | ❌ | ❌ | ❌ |
| Real-time live feed | ✅ | ✅ | ✅ | ✅ |
| Export as curl | ✅ | ❌ | ✅ | ❌ |
| Price | **Free** | Free (limited) | Free (limited) | $25/mo |

---

## Features

- **🪣 Buckets** — Organize webhooks by project or service; each gets a unique capture URL
- **⚡ Live feed** — New requests appear in real-time via SSE, no polling, no page reload
- **🔍 Full inspection** — View method, headers, body (JSON-highlighted), query params
- **↺ Replay** — Resend any captured request to a different URL (great for local dev)
- **⇒ Auto-forward** — Optionally forward every incoming request to your local server automatically
- **📋 Export as curl** — One-click curl command for any request
- **🔔 Telegram notifications** — Get a message when a webhook arrives (optional, per bucket)
- **🗑️ Request retention** — Configurable per-bucket cap and TTL (default 500 req / 30 days)
- **🐳 Docker-first** — One command to run, SQLite embedded, no external dependencies

---

## Quick Start

```bash
# Clone
git clone https://github.com/colapsis/hookpilot.git
cd hookpilot

# Configure (optional)
cp .env.example .env
# Edit BASE_URL to your public server address

# Run
docker compose up -d

# Open
open http://localhost:8000
```

That's it. No database server, no message broker, no API key.

---

## Usage

### 1. Create a bucket

Click **New Bucket**, give it a name (e.g. `stripe-dev`), and optionally:
- Add a description
- Set an **auto-forward URL** (all incoming webhooks will be proxied there)
- Set a **Telegram Chat ID** for notifications

### 2. Point your webhook at the capture URL

```
POST http://your-server:8000/w/stripe-dev
```

Any HTTP method works: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`.

### 3. Inspect in real-time

Open the bucket in your browser. New requests appear live as they arrive — click any to inspect headers, body, and query params.

### 4. Replay to your local dev server

Click **Replay**, enter your local URL (e.g. `http://localhost:3000/webhook`), hit **Send**. HookPilot forwards the exact same headers and body and shows you the response status and latency.

### 5. Copy as curl

Click **Copy as curl** to get a ready-to-paste shell command — useful for teammates or CI scripts.

---

## Configuration

All settings via environment variables (or `.env` file):

| Variable | Default | Description |
|---|---|---|
| `BASE_URL` | `http://localhost:8000` | Public URL shown in webhook links |
| `TELEGRAM_BOT_TOKEN` | _(empty)_ | Bot token from @BotFather (enables notifications) |
| `REQUEST_RETENTION_DAYS` | `30` | Delete requests older than N days (0 = keep forever) |
| `MAX_REQUESTS_PER_BUCKET` | `500` | Cap per bucket, oldest removed first |
| `MAX_BODY_SIZE` | `524288` | Max captured body size in bytes (512 KB) |
| `DATABASE_PATH` | `./data/hookpilot.db` | SQLite file path |

---

## Running without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

---

## REST API

HookPilot ships a REST API (documented at `/api/docs`):

```
GET    /              Dashboard
GET    /b/{slug}       Bucket view (live)
GET    /r/{id}         Request detail

POST   /api/buckets            Create bucket
PATCH  /api/buckets/{slug}     Update bucket
DELETE /api/buckets/{slug}     Delete bucket

GET    /api/buckets/{slug}/requests    List requests
GET    /api/requests/{id}              Get request + replays
DELETE /api/requests/{id}             Delete request
GET    /api/requests/{id}/curl         Export as curl
POST   /api/requests/{id}/replay       Replay to URL

GET    /api/stream/{slug}      SSE live event stream
GET    /api/stats              Global stats

ANY    /w/{slug}               Webhook capture endpoint
```

---

## Deployment on a VPS

```bash
# Set your public URL
echo "BASE_URL=https://hooks.yourdomain.com" > .env

# Run behind nginx (recommended)
docker compose up -d
```

Example nginx config:
```nginx
server {
    listen 443 ssl;
    server_name hooks.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # Required for SSE (live feed)
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600;
    }
}
```

---

## Tech Stack

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/) + [aiosqlite](https://github.com/omnilib/aiosqlite)
- **Frontend**: [htmx](https://htmx.org/) + [Tailwind CSS](https://tailwindcss.com/) (CDN, no build step)
- **Syntax highlighting**: [Prism.js](https://prismjs.com/)
- **Notifications**: Telegram Bot API
- **Real-time**: Server-Sent Events (SSE)

---

## Contributing

PRs welcome. To run tests:

```bash
pip install -r requirements.txt pytest httpx
pytest
```

---

## License

MIT — see [LICENSE](LICENSE).
