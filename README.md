# Ardee RAG ChatBot

Production-grade **RAG (Retrieval-Augmented Generation) chatbot** with a FastAPI backend and a Next.js dashboard. Admins create **bots** (each with its own system prompt and PDF knowledge base); users get **streamed, citation-backed answers** grounded strictly in that bot's documents — with a hard guard against hallucination.

## Live deployment

This project is currently deployed on **Render** using the root [`render.yaml`](render.yaml) blueprint.

| Service | URL |
|---|---|
| Frontend | https://ardee-frontend.onrender.com |
| Backend | https://ardee-backend.onrender.com |
| Backend health check | https://ardee-backend.onrender.com/api/v1/health |
| Backend API docs | https://ardee-backend.onrender.com/docs |

Render free-tier services can go to **sleep after inactivity**. When that happens, the first frontend/API request wakes the backend and may take extra time. After the service is awake, later requests are much faster.

> For **feature design**, end-to-end workflows, and the roadmap, see **[ARCHITECTURE.md](ARCHITECTURE.md)**.
>
> For **production-grade system design** — layered backend, hybrid retrieval, confidence gating, Redis caching & rate limiting, auth/RBAC, observability, connection pooling, and the scaling path (S3 + async workers) — see the same doc: [System overview](ARCHITECTURE.md#system-overview), [End-to-end workflows](ARCHITECTURE.md#end-to-end-workflows), and [Scope of improvement](ARCHITECTURE.md#scope-of-improvement).

---

## Feature checklist
Everything below is implemented and working in this repo — useful both as a product summary and as talking points in an interview.
### Core product

- [x] **Multi-bot assistants** — each bot has its own system prompt + PDF knowledge base; retrieval never crosses bots
- [x] **PDF ingestion pipeline** — upload → extract (pypdf) → chunk (LlamaIndex) → embed (OpenAI) → store in pgvector
- [x] **Hybrid retrieval** — vector (pgvector/HNSW) + keyword (Postgres FTS) fused with Reciprocal Rank Fusion
- [x] **Citation-backed answers** — responses cite source file and page number
- [x] **Streaming chat (SSE)** — token-by-token answers instead of waiting for the full response
- [x] **Anti-hallucination confidence gate** — low relevance → refuse to answer; LLM is not called
- [x] **Greeting / small-talk handling** — friendly replies without fake document answers
- [x] **Semantic answer cache (Redis)** — similar questions on the same bot return instantly at zero LLM cost
- [x] **Multi-turn chat sessions** — history fed into the prompt; rename / delete sessions
- [x] **Admin console** — bot CRUD, PDF manage (upload / rename / replace / delete), usage charts
- [x] **Auth + RBAC** — JWT access/refresh, bcrypt passwords, `ADMIN` / `USER` roles

## Additional Features

- [x] **Cost & abuse controls** — Redis rate limiting, semantic cache, per-user / per-bot token accounting
- [x] **Observability** — structured logging (structlog), `X-Request-ID` tracing, Prometheus metrics endpoint
- [x] **Security hardening** — security-headers middleware, short-lived access tokens, role-gated admin APIs
- [x] **Async data layer** — async SQLAlchemy + connection pooling (pre-ping, recycle, bounded pool)
- [x] **One DB for vectors + relational data** — Postgres + pgvector (HNSW) + full-text search, no separate vector store
- [x] **Schema migrations** — Alembic (pgvector extension, FTS trigger, bots scoping)
- [x] **Clean layered architecture** — routes → services → repositories → models; documented in `ARCHITECTURE.md`
- [x] **Automated quality gates** — pytest suite, Ruff, mypy, pre-commit hooks
- [x] **Reproducible local/demo setup** — Docker Compose, Makefile, idempotent seed script (users + default bot)
- [x] **Deployable blueprint** — `render.yaml` for Postgres, Redis, backend, and frontend
- [x] **Honest refusal UX** — explicit low-confidence message instead of hallucinating when docs don’t cover the question
- [x] **Modern full-stack surface** — FastAPI + Next.js 15 / React 19 TypeScript UI with live streaming and citations

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, React 19, TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.13, async SQLAlchemy 2.0 |
| Database | PostgreSQL 16 + **pgvector** (HNSW index) + full-text search |
| Cache / Rate limit | Redis 7 |
| RAG | OpenAI embeddings + chat, LlamaIndex chunking, pypdf extraction |
| Auth | JWT (access + refresh), passlib/bcrypt, RBAC |
| Observability | structlog, Prometheus-compatible `/api/v1/metrics` |
| Tooling | uv, Ruff, mypy, pytest; ESLint, tsc |
| Deployment | Docker, Docker Compose |

---

## Functionality

**Authentication & access**
- User registration and login (OAuth2 password flow), JWT access + refresh tokens.
- Role-based access control: `ADMIN` and `USER`. Token carries the user's display name.

**Bots**
- Admins create bots with a name, description, and system prompt; soft-delete and deactivate as needed.
- Any authenticated user can list active bots and open a chat.
- Knowledge-base PDFs are attached per bot; hybrid search never crosses bots.

**RAG chat**
- Ask questions against a selected bot; answers **stream live** and cite the source file + page.
- Retrieval is **hybrid** (vector + keyword, RRF-fused), typically top 3 chunks from the UI.
- **Low-confidence guard**: no relevant context → `"I do not have enough information in the uploaded documents to answer this question."` (no LLM call).
- **Greeting detection**: social messages get a conversational LLM reply without touching the documents.
- **Semantic cache** (Redis, per bot): similar questions return cached answers instantly.
- Per-session chat history (last *K* turns) fed back into the prompt; sessions belong to a user + bot.
- Users can **rename** and **delete** their chat sessions.

**Admin document management**
- Upload a PDF to a bot (**title required**), rename, replace the file (re-indexed, version bumped), or delete — with confirmation prompts.
- Ingestion pipeline: extract (pypdf) → chunk (LlamaIndex) → embed (OpenAI) → store in pgvector.

**Metrics & usage**
- Per-user and **per-bot** token usage for admins, with a working refresh.
- Daily token-usage chart (tokens in **1K**, x-axis = day), filterable by user or bot.
- Each user can see their own total and per-session usage.
- Prometheus-compatible HTTP and RAG business metrics at `/api/v1/metrics`.

**Platform**
- Async DB connection pool, Redis-backed rate limiting, request-ID correlation (`X-Request-ID`), security-headers middleware, structured logging.

---

## Run with Docker (recommended)

This starts the **backend, PostgreSQL (pgvector), and Redis** together, then runs migrations and seeds baseline accounts.

**1. Configure environment**

```bash
cp .env.example .env
# edit .env and set at least:
#   OPENAI_API_KEY=sk-...
#   POSTGRES_PASSWORD=<something strong>
#   JWT_SECRET_KEY=<random 64-char string>
```

**2. Build and start all services**

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

**3. Apply database migrations** (creates tables, enables pgvector + the full-text trigger)

```bash
docker compose -f docker/docker-compose.yml exec backend alembic upgrade head
```

**4. Seed baseline accounts** (2 admins + 6 users + a default bot, idempotent)

```bash
docker compose -f docker/docker-compose.yml exec backend python -m scripts.seed_staging
```

The command prints the shared password for the seeded accounts (default `StagingPass123!`; override with `SEED_PASSWORD=...` or `--password`). It also creates a **General Knowledge Assistant** bot (and backfills any bot-less documents/sessions). It **refuses to run when `APP_ENV=production`** unless you pass `--force`.

**5. Start the frontend**

The compose file runs the backend and infrastructure. The Next.js frontend is run separately:

```bash
make frontend-run
```

**6. Open the app**

| What | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Health check | http://localhost:8000/api/v1/health |
| Metrics | http://localhost:8000/api/v1/metrics |

> The **frontend** is a separate Next.js app (not in the compose file). Use `make frontend-run` from the repo root.

**Stop / logs**

```bash
docker compose -f docker/docker-compose.yml logs -f backend
docker compose -f docker/docker-compose.yml down          # keep data
docker compose -f docker/docker-compose.yml down -v       # also wipe volumes
```

---

## Run locally with Make

This is the day-to-day development flow. Run the backend and frontend on your machine with hot reload using `make run` and `make frontend-run`.

### 1. Configure env files

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env.local
```

Edit `.env` and set at least:

```bash
OPENAI_API_KEY=sk-...
POSTGRES_PASSWORD=<same password your database uses>
JWT_SECRET_KEY=<random 64-char string>
```

For local frontend development, `frontend/.env.local` should usually contain:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

### 2. Start Postgres and Redis

If you want Docker only for dependencies, start just Postgres and Redis:

```bash
docker compose -f docker/docker-compose.yml up -d postgres redis
```

If you do not want Docker at all, install/start PostgreSQL 16 with the `pgvector` extension and Redis locally, then make sure the `POSTGRES_*` and `REDIS_*` values in `.env` match those services.

### 3. Install dependencies

```bash
cd backend && uv sync --all-extras
cd ../frontend && npm install
```

### 4. Prepare the database

Run this before chatting or uploading documents:

```bash
cd backend
uv run alembic upgrade head
uv run python -m scripts.seed_staging
```

`alembic upgrade head` creates the database schema, enables `pgvector`, and sets up indexes/triggers used by hybrid retrieval. The seed command is optional but recommended for local/demo use because it creates baseline admin/user accounts and a default bot.

You can also run the seed script from the repo root:

```bash
make seed-staging
```

### 5. Run the app

From the repo root, start the backend:

```bash
make run                             # start FastAPI on :8000 (hot reload)
```

In a second terminal from the repo root, start the frontend:

```bash
make frontend-run                    # start Next.js on :3000
```

Sign in with a seeded account (e.g. `admin@ardee.test`). Everyone lands on **Bots**; admins also have the **Console** for usage metrics and can manage each bot's prompt and PDFs.

---

## Seed data

`backend/scripts/seed_staging.py` creates **2 admins and 6 users** (all `@ardee.test`) plus a default bot. It is **idempotent** — existing emails/bots are skipped — so it is safe to re-run. It refuses to run against a production environment unless `--force` is passed.

```bash
# in Docker
docker compose -f docker/docker-compose.yml exec backend python -m scripts.seed_staging

# on host (from backend/)
uv run python -m scripts.seed_staging
SEED_PASSWORD='YourStagingPass1!' uv run python -m scripts.seed_staging

# or from the repo root
make seed-staging
```

---

## Useful commands

```bash
make dev             # Install dev dependencies and setup pre-commit
make run             # Run FastAPI backend on :8000 with hot reload
make frontend-run    # Run Next.js frontend on :3000
make seed-staging    # Seed 2 admins + 6 users + default bot
make docker-up       # Start Docker Compose services
make docker-down     # Stop Docker Compose services
make docker-logs     # Tail Docker Compose logs
make test            # Backend tests (pytest)
make lint            # Ruff
make typecheck       # mypy
make check           # lint + typecheck
make frontend-build  # Build frontend for production
```

---

## Render deployment

Render uses [`render.yaml`](render.yaml) to provision:

- PostgreSQL 16 with `pgvector`
- Redis
- FastAPI backend Docker service
- Next.js frontend Docker service

The backend startup script [`backend/scripts/start.sh`](backend/scripts/start.sh) runs:

```bash
alembic upgrade head
uvicorn app.main:app
```

For a one-time baseline seed on Render, set `SEED_ON_START=true` on the backend service for one deploy, then set it back to `false`. The seed script is idempotent, but it should not be left enabled forever.

Important Render environment values:

| Service | Variable | Value |
|---|---|---|
| Backend | `OPENAI_API_KEY` | Your OpenAI API key |
| Backend | `CORS_ORIGINS` | `https://ardee-frontend.onrender.com` |
| Frontend | `NEXT_PUBLIC_API_BASE_URL` | `https://ardee-backend.onrender.com/api/v1` |

Because the current services are on Render free tier, the backend may sleep after inactivity. The first request after sleep acts as a wake-up request and can be slow.

---

## Key API endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Get access + refresh tokens |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| GET | `/api/v1/bots` | List active bots |
| POST | `/api/v1/bots` | Admin: create bot |
| GET | `/api/v1/bots/{id}` | Bot detail + documents |
| PATCH | `/api/v1/bots/{id}` | Admin: update bot |
| DELETE | `/api/v1/bots/{id}` | Admin: soft-delete bot |
| GET | `/api/v1/bots/{id}/documents` | List bot knowledge-base PDFs |
| POST | `/api/v1/bots/{id}/documents` | Admin: upload PDF to bot |
| POST | `/api/v1/chat/ask` | Ask (non-streaming; requires `bot_id` for new sessions) |
| POST | `/api/v1/chat/ask/stream` | Ask (SSE streaming) |
| GET | `/api/v1/chat/sessions` | List my sessions |
| GET | `/api/v1/chat/sessions/{id}` | Session history |
| PATCH | `/api/v1/chat/sessions/{id}` | Rename session |
| DELETE | `/api/v1/chat/sessions/{id}` | Delete session |
| GET | `/api/v1/chat/usage/me` | My token usage (total + per session) |
| POST | `/api/v1/rag/documents` | Admin: upload PDF (`bot_id` required) |
| GET | `/api/v1/rag/documents` | Admin: list PDFs (optional `bot_id`) |
| PATCH | `/api/v1/rag/documents/{id}` | Admin: rename |
| PUT | `/api/v1/rag/documents/{id}/file` | Admin: replace file |
| DELETE | `/api/v1/rag/documents/{id}` | Admin: delete |
| POST | `/api/v1/rag/search` | Hybrid search (requires `bot_id`) |
| GET | `/api/v1/admin/metrics/token-usage/users` | Admin: per-user usage |
| GET | `/api/v1/admin/metrics/token-usage/bots` | Admin: per-bot usage |
| GET | `/api/v1/admin/metrics/token-usage/daily` | Admin: daily usage series |
| GET | `/api/v1/metrics` | Prometheus metrics |

---

## Project structure

```text
backend/
  app/
    api/            # FastAPI routes (auth, bots, chat, rag_documents, rag_search, metrics, health)
    core/           # config, database, redis, logging, metrics, security, exceptions
    middleware/     # request id, rate limit, security headers, metrics
    models/         # SQLAlchemy models (user, rag / bots)
    repositories/   # data access (user, bot, chat, rag_document, rag_retrieval, metrics)
    schemas/        # Pydantic schemas
    services/       # business logic (bot, chat, rag_retrieval, pdf_ingestion, pdf_storage,
                    #                  semantic_cache, rag_document, greeting)
  alembic/          # database migrations
  scripts/          # operational scripts (seed_staging.py)
  tests/            # backend tests
frontend/
  src/
    app/            # Next.js routes (login, bots, usage, admin)
    components/     # ChatWorkspace, BotFormModal, DocumentsPanel, UsageChart, ...
    lib/            # api client (incl. SSE), auth, types
docker/             # Dockerfile + docker-compose (backend, postgres, redis)
Makefile            # developer commands
ARCHITECTURE.md     # functionality, benefits, workflows, and roadmap
```

---

## Configuration

All configuration is environment-driven (12-factor). Key variables (see `.env.example`):

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | OpenAI key for embeddings + chat |
| `APP_ENV` | `development` / `staging` / `production` |
| `APP_LOG_LEVEL` | Log level (default `INFO`) |
| `DB_ECHO` | `true` to log SQL (routed through structlog) |
| `POSTGRES_*` | Database connection |
| `REDIS_*` | Cache / rate-limit connection |
| `JWT_SECRET_KEY` | JWT signing secret |
| `RATE_LIMIT_PER_MINUTE` | Requests/min per user (default 60) |
| `RAG_TOP_K` | Chunks retrieved (default 5; chat UI often requests 3) |
| `RAG_MIN_VECTOR_SCORE` | Min vector similarity for confidence gate |
| `SEMANTIC_CACHE_THRESHOLD` | Cosine similarity for cache hits |
| `CHAT_HISTORY_MESSAGES_LIMIT` | Prior messages included in answers |
| `SEED_PASSWORD` | Password for seeded accounts |

---

## Production notes

- Never commit `.env`; rotate any leaked OpenAI/JWT/Postgres/Redis secrets.
- Set `APP_ENV=production`, a strong `JWT_SECRET_KEY`, and exact `CORS_ORIGINS`.
- Always run `alembic upgrade head` before serving traffic.
- Put TLS/HTTPS in front via a reverse proxy or load balancer.
- See **[ARCHITECTURE.md](ARCHITECTURE.md)** for the scaling roadmap (S3 storage, async ingestion workers, observability, CI/CD).
