# Ardee RAG ChatBot

A production-grade Retrieval-Augmented Generation (RAG) chatbot with authentication, admin panel, hybrid search, semantic cache, chat history, metrics dashboard, and Docker deployment.

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.13, FastAPI, Async SQLAlchemy, Alembic |
| **Frontend** | Next.js, React, TypeScript, TailwindCSS, shadcn/ui |
| **LLM** | OpenAI GPT-4o via LlamaIndex |
| **Embeddings** | OpenAI text-embedding-3-small |
| **Vector DB** | PostgreSQL + pgvector |
| **Search** | Hybrid (Dense + BM25) |
| **Cache** | Redis (semantic cache) |
| **Auth** | JWT (access + refresh tokens), bcrypt, RBAC |
| **Deployment** | Docker, Docker Compose |

## Project Structure

```
├── backend/          # FastAPI application (Clean Architecture)
│   ├── app/
│   │   ├── api/          # API routes (versioned)
│   │   ├── core/         # Cross-cutting concerns
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── services/     # Business logic
│   │   ├── repositories/ # Data access layer
│   │   └── middleware/   # Custom middleware
│   ├── tests/
│   └── alembic/          # Database migrations
├── frontend/         # Next.js application
├── docker/           # Docker configurations
└── Makefile          # Developer commands
```

## Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [pnpm](https://pnpm.io/) (Node.js package manager)
- Docker & Docker Compose

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/nikhileshsirohi/ARDEE-RAG-CHATBOT.git
cd Ardee-RAG-ChatBot

# 2. Install dependencies (creates venv automatically)
make dev

# 3. Start infrastructure (PostgreSQL + Redis)
make docker-up

# 4. Start the backend server
make run

# 5. Open in browser
open http://localhost:8000/docs
```

### Available Commands

```bash
make help         # Show all available commands
make dev          # Install all dependencies + set up pre-commit
make run          # Start FastAPI dev server
make test         # Run tests
make lint         # Run Ruff linter
make format       # Format code (Black + Ruff)
make typecheck    # Run mypy
make check        # Run all quality checks
make docker-up    # Start PostgreSQL + Redis
make docker-down  # Stop infrastructure
make clean        # Remove caches
```

### Environment Variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

See [`.env.example`](.env.example) for all available configuration options.

## API Documentation

When running in development mode:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

> API docs are disabled in production for security.

## Development

### Code Quality

This project enforces code quality via pre-commit hooks:

- **Ruff** — Linting + import sorting (replaces flake8, isort)
- **Black** — Code formatting
- **mypy** — Static type checking

Hooks run automatically on every commit. Run manually:

```bash
make check
```

## License

MIT
