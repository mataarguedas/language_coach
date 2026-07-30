# Pronunciation Coach

Voice-driven pronunciation practice for **Mandarin (`zh`), Spanish (`es`), and English (`en`)**. See [PRD.md](./PRD.md) for product scope and [CLAUDE.md](./CLAUDE.md) for engineering guidance.

## Repo layout

```
/frontend   React + Vite + TS + Tailwind (deploys to Vercel)
/backend    FastAPI (Docker, deploys to Railway with a mounted cache volume)
```

## Local development

### Everything via docker compose (recommended)

Bring up backend + frontend in one command:

```bash
docker compose up --build
# Frontend: http://localhost:5173  (Vite dev server with HMR)
# Backend:  http://localhost:8000  (health at /api/health)
```

The frontend container bind-mounts `./frontend` for hot module reload, and the backend's audio cache is persisted in a named Docker volume (`backend_cache`). Stop with `Ctrl+C`; `docker compose down` removes the containers, `docker compose down -v` also wipes the cache.

Provider keys are still **BYOK** — enter them in the app's **API Keys** panel after it loads. Nothing key-related is set in `docker-compose.yml`.

### Backend

Requires Python 3.11+ and system `ffmpeg` + `libsndfile1` (for `librosa`).

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # optional; defaults work for local dev
uvicorn app.main:app --reload --port 8000
```

Health check:

```bash
curl http://localhost:8000/api/health
# {"status":"ok"}
```

Tests:

```bash
pytest -q
```

### Backend via Docker (mirrors production)

```bash
cd backend
docker build -t pronunciation-coach-backend .
docker run --rm -p 8000:8000 \
  -e ALLOWED_ORIGINS=http://localhost:5173 \
  -v $(pwd)/cache:/data/cache \
  pronunciation-coach-backend
```

The container runs as a non-root user (`app`, uid 10001) and exposes a Docker `HEALTHCHECK` that hits `/api/health`.

### Frontend

Requires Node 20+.

```bash
cd frontend
npm install
npm run dev
# http://localhost:5173  (Vite proxies /api → http://localhost:8000)
```

Tests / typecheck:

```bash
npm run test
npm run typecheck
```

## Environment variables

### Backend (server-side, set on Railway)

| Var | Required | Default | Purpose |
|---|---|---|---|
| `ALLOWED_ORIGINS` | **yes in prod** | `http://localhost:5173` | Comma-separated CORS allow-list. Must contain the exact Vercel origin(s), including protocol, no trailing slash. |
| `CACHE_DIR` | no | `/data/cache` | Filesystem path for the audio cache. Point at the Railway volume mount. |
| `PORT` | no | `8000` | Bind port. Railway injects this automatically. |

**BYOK provider keys are never server env vars.** The browser sends them per-request as HTTP headers; the backend forwards to the provider and never persists or logs them.

| Header | Required for | Notes |
|---|---|---|
| `X-Fish-Key` | all TTS synthesis | Fish Audio hosted API. |
| `X-OpenAI-Key` | Mandarin (`zh`) segmentation | Not sent / not required for `es` or `en`. |
| `X-Azure-Speech-Key` | pronunciation scoring | Strict opt-in. Absent → `/shadow/analyze` returns prosody with `pronunciation: null`. |
| `X-Azure-Speech-Region` | pronunciation scoring | Azure region slug, e.g. `westus`, `eastus`, `westeurope`. Both Azure headers must be present together. |

If Azure is invoked but fails (bad key, transient 5xx, malformed response), the request still succeeds with `pronunciation: null` and a human-readable `pronunciation_error` string — prosody is never dropped because pronunciation broke ([CLAUDE.md](./CLAUDE.md) "Independence").

### Frontend (build-time, set on Vercel)

| Var | Required | Purpose |
|---|---|---|
| `VITE_API_URL` | **yes in prod** | Absolute URL of the deployed backend, e.g. `https://pronunciation-coach-api.up.railway.app`. No trailing slash. Leave empty locally to use the Vite dev proxy. |

`.env.example` files are provided in both `frontend/` and `backend/`.

## Deploy — end to end

The two services are deployed independently. Bring the backend up first so the frontend build has a real URL to point at.

### 1. Backend → Railway (Docker + volume)

1. Push the repo to GitHub.
2. In Railway: **New Project → Deploy from GitHub repo**, then set the service **Root Directory** to `backend/`. Railway auto-detects the `Dockerfile`.
3. **Add a Volume** to the service (Settings → Volumes):
   - Mount path: `/data`
   - Size: 1 GB is plenty to start (the cache is small MP3 files).
   The `CACHE_DIR` env var already defaults to `/data/cache`, which lives on this volume — audio persists across deploys and restarts.
4. Set env vars (Settings → Variables):
   - `ALLOWED_ORIGINS` — your Vercel production URL, plus any preview URL patterns you want to allow, comma-separated. Example: `https://pronunciation-coach.vercel.app,https://pronunciation-coach-git-main-you.vercel.app`
   - Leave `CACHE_DIR` and `PORT` unset unless you need to override.
5. Deploy. Confirm health at `https://<your-service>.up.railway.app/api/health`.
6. Copy the public URL — you'll need it for the frontend.

### 2. Frontend → Vercel

1. In Vercel: **Add New Project → Import** from the same GitHub repo, then set the project **Root Directory** to `frontend/`. Vercel picks up `frontend/vercel.json` (framework preset: Vite, build command, SPA rewrite).
2. Set env vars (Project Settings → Environment Variables):
   - `VITE_API_URL` = the Railway URL from step 1 (no trailing slash).
   Apply to **Production**, and to **Preview** if you also want preview deploys wired up.
3. Deploy. Vercel runs `npm run build`, serves `dist/`, and the SPA rewrite ensures deep links resolve to `index.html`.
4. Open the deployed URL, expand **API Keys**, enter your Fish Audio key (and OpenAI key if practising Mandarin), and try a synthesis.

### 3. After the first deploy — tightening CORS

Once both URLs are stable, update Railway's `ALLOWED_ORIGINS` to the exact set of Vercel origins that should reach the backend and redeploy the backend service. CORS is deliberately allow-listed (no `*`, `allow_credentials=False`) so a wrong origin fails visibly in the browser console.

## Security & cost guardrails baked in

- **BYOK, no persistence** — keys live in the browser's `sessionStorage`, sent per-request as headers, never logged, never on disk, never in cache keys or error messages.
- **CORS allow-list** — driven by `ALLOWED_ORIGINS`; no wildcard.
- **Cache-first** — every `/api/synthesize` checks the disk cache (keyed by `sha256(text + language + voice_id + speed)`) before calling Fish. Identical requests never re-bill.
- **No LLM spend on `es`/`en`** — segmentation there is a local deterministic tokenizer. OpenAI is only called on the `zh` path, and only on a cache miss.
- **Input caps** — 500-char text limit on synthesis; 30-second / 20 MB caps on shadowing uploads. Over-limit requests return `413`/`422` with an explanatory `detail`.
- **Non-root container** — the backend image runs as `app:10001` and ships without build tools in the final layer.
