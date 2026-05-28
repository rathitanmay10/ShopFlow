# Getting started

## Prerequisites

- Python 3.13 (`.python-version` pins it)
- [`uv`](https://docs.astral.sh/uv/) — package manager (lockfile is `uv.lock`)
- Docker + Docker Compose (for Postgres + Redis)

## Local quickstart

```bash
# 1. Install
uv sync

# 2. Configure
cp .env.example .env
# Generate a JWT secret and paste it in:
openssl rand -hex 32

# 3. Start Postgres + Redis
docker compose up postgres redis -d

# 4. Migrate
uv run alembic upgrade head

# 5. Run API + worker (separate terminals)
uv run uvicorn app.main:app --reload
uv run arq app.workers.tasks.WorkerSettings
```

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>

## Docker quickstart

```bash
docker compose up --build
```

Brings up `postgres`, `redis`, `migrate` (one-shot), `api`, `worker`. API listens on `:8000`.

The compose `api`, `worker`, and `migrate` services override `DATABASE_URL` / `REDIS_URL` to use service names — `.env` doesn't need editing.

## Environment

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | yes | — | `postgresql+asyncpg://user:pass@host:5432/db` |
| `TEST_DATABASE_URL` | tests only | falls back to `DATABASE_URL` | pytest target |
| `REDIS_URL` | yes | `redis://localhost:6379/0` | ARQ broker + rate limit |
| `JWT_SECRET` | yes | — | `openssl rand -hex 32` |
| `JWT_ACCESS_TTL_MINUTES` | no | `15` | |
| `JWT_REFRESH_TTL_DAYS` | no | `14` | |
| `CORS_ORIGINS` | no | empty | comma-separated |
| `PAYMENT_SUCCESS_RATE` | no | `0.8` | 0.0–1.0; controls payment simulator |
| `RATE_LIMIT_DEFAULT_PER_MIN` | no | `120` | per IP, fixed window |
| `RATE_LIMIT_AUTH_PER_MIN` | no | `5` | failed logins per IP+email |
| `LOW_STOCK_THRESHOLD` | no | `5` | emit `low_stock` event below this |

Full list: `.env.example` in repo root.

## Common commands

```bash
# deps
uv sync
uv add "<pkg>>=X.Y,<X.Z"
uv add --dev "<pkg>>=X.Y,<X.Z"

# dev server
uv run uvicorn app.main:app --reload

# alembic
uv run alembic revision --autogenerate -m "msg"
uv run alembic upgrade head

# worker
uv run arq app.workers.tasks.WorkerSettings

# lint / format / typecheck
uv run ruff check .
uv run ruff format .
uv run ty check app

# tests
uv run pytest
uv run pytest tests/api/test_orders.py::test_cancel_restores_stock
uv run pytest -k race -x
uv run pytest --cov=app
```
