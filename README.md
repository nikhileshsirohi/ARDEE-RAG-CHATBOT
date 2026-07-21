# Ardee RAG ChatBot

Enterprise RAG chatbot backend built with FastAPI, PostgreSQL + pgvector, Redis, OpenAI, JWT authentication, RBAC, chat history, semantic cache, admin PDF management, metrics, and production middleware.

The backend is implemented. The Next.js frontend/admin dashboard is still pending.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Python 3.13, Async SQLAlchemy |
| Database | PostgreSQL + pgvector |
| Cache | Redis |
| RAG | OpenAI embeddings, GPT model, PDF ingestion |
| Auth | JWT access tokens, refresh tokens, RBAC |
| Monitoring | Prometheus-compatible `/api/v1/metrics` |
| Deployment | Docker, Docker Compose |

## Current Functionality

- User registration and login
- JWT authentication with refresh tokens
- Role-based access control: `ADMIN` and `USER`
- Admin-only PDF upload, update, replace, delete
- PDF text extraction, chunking, embeddings, and pgvector storage
- Vector-based RAG retrieval
- RAG chatbot with user-owned chat sessions
- Latest K chat history support
- Low-confidence guard to avoid hallucination
- Redis semantic cache for similar questions
- Chat response returns semantic cache hit and similarity score
- Admin token usage metrics per user
- Prometheus-compatible HTTP and RAG business metrics
- Redis-backed rate limiting
- Request ID correlation using `X-Request-ID`
- Security headers middleware
- Docker Compose for backend, PostgreSQL, and Redis

## Project Structure

```text
backend/
  app/
    api/             # FastAPI routes
    core/            # config, database, redis, logging, metrics
    middleware/      # request id, rate limit, security headers, metrics
    models/          # SQLAlchemy models
    repositories/    # data access
    schemas/         # Pydantic schemas
    services/        # business logic
  alembic/           # database migrations
  tests/             # backend tests
docker/              # Dockerfile and docker-compose
Makefile             # developer commands
```

## How To Run

1. Copy env file:

```bash
cp .env.example .env
```

2. Add your OpenAI key in `.env`:

```bash
OPENAI_API_KEY=your-key
```

3. Install backend dependencies:

```bash
cd backend
uv sync --all-extras
cd ..
```

4. Start PostgreSQL and Redis:

```bash
make docker-up
```

5. Run migrations:

```bash
cd backend
uv run alembic upgrade head
cd ..
```

6. Start backend:

```bash
make run
```

Open API docs:

```text
http://localhost:8000/docs
```

Health check:

```bash
curl http://localhost:8000/api/v1/health
```

Metrics:

```bash
curl http://localhost:8000/api/v1/metrics
```

## Useful Commands

```bash
make run          # Run FastAPI backend
make docker-up    # Start backend dependencies / compose services
make docker-down  # Stop Docker services
make test         # Run backend tests
make lint         # Run Ruff
make typecheck    # Run mypy
make check        # Run lint + typecheck
```

Direct test command:

```bash
backend/.venv/bin/python -m pytest
```

## Important API Areas

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/rag/documents` admin PDF upload
- `GET /api/v1/rag/documents` admin document list
- `PATCH /api/v1/rag/documents/{document_id}` admin metadata update
- `PUT /api/v1/rag/documents/{document_id}/file` admin PDF replace
- `DELETE /api/v1/rag/documents/{document_id}` admin PDF delete
- `POST /api/v1/chat/ask` ask chatbot
- `GET /api/v1/chat/sessions` list user sessions
- `GET /api/v1/chat/sessions/{session_id}` view session messages
- `GET /api/v1/admin/metrics/token-usage/users` admin user token metrics
- `GET /api/v1/metrics` Prometheus metrics

## What Is Pending

- Next.js frontend UI
- Admin dashboard UI for documents and metrics
- User chatbot UI with sessions/history
- Full end-to-end application testing with frontend + backend
- CI/CD pipeline
- Production deployment setup
- TLS/HTTPS through reverse proxy or load balancer
- Managed PostgreSQL/Redis or hardened infrastructure
- Backup and restore strategy
- Prometheus/Grafana deployment and dashboards
- Log shipping with request ID correlation
- Load testing for uploads, retrieval, chat, Redis cache, and rate limits
- Secret rotation and production secret manager integration

## Production Notes

- Do not commit `.env`.
- Rotate any leaked OpenAI/JWT/Postgres/Redis secrets before production.
- Set `APP_ENV=production`.
- Set exact `CORS_ORIGINS` for the deployed frontend.
- Run `uv run alembic upgrade head` before starting the backend.
- Use `http://localhost:8000/docs` locally. Do not use `0.0.0.0` in the browser.

