# ShopFlow

Event-driven e-commerce backend. Fully-async FastAPI + PostgreSQL + Redis + ARQ workers.

See [`CLAUDE.md`](./CLAUDE.md) for architecture, conventions, and dependency-pinning policy.

## Stack

- Python 3.13, FastAPI, Pydantic v2
- SQLAlchemy 2.x async (`asyncpg`), Alembic
- Redis + ARQ (background tasks)
- JWT auth (bcrypt password hashing)
- Tooling: `uv`, `ruff`, `ty`, `pytest`, `pre-commit`

## Quickstart (local)

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

Swagger UI: <http://localhost:8000/docs> · ReDoc: <http://localhost:8000/redoc>

## Quickstart (Docker)

```bash
docker compose up --build
```

Brings up `postgres`, `redis`, `migrate` (one-shot), `api`, `worker`. API listens on `:8000`.

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
| `PAYMENT_MAX_RETRIES` | no | `3` | |
| `RATE_LIMIT_DEFAULT_PER_MIN` | no | `120` | per IP, fixed window |
| `RATE_LIMIT_AUTH_PER_MIN` | no | `5` | failed logins per IP+email |
| `LOW_STOCK_THRESHOLD` | no | `5` | emit `low_stock` event below this |

Full list: see [`.env.example`](./.env.example).

## Layout

```
app/
├── api/v1/         routers: auth, categories, products, inventory, orders, admin
├── core/           config, security (JWT + bcrypt), exceptions, logging
├── db/             async engine, session factory, Base
├── models/         SQLAlchemy 2.x ORM
├── schemas/        Pydantic v2 DTOs
├── repositories/   SQL access (one per aggregate root)
├── services/       business logic (orchestrates repos)
├── workers/        ARQ tasks (payment, notifications) + WorkerSettings, queue helper
├── middleware/     request-context (request-id, access log), rate-limit
├── utils/
└── main.py         app factory
alembic/            migrations 0001..0007
tests/              conftest, api/, services/  (httpx.AsyncClient, transactional rollback)
scripts/            export_postman.py
```

Layering: **API → Service → Repository → DB**. Routers never touch SQLAlchemy. Services never open sessions. Repositories never call other repos.

## Endpoints (v1)

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/register` | public | creates user, default role `customer` |
| POST | `/auth/login` | public | returns access + refresh; throttled per IP+email |
| POST | `/auth/refresh` | public | rotates token pair |
| GET | `/categories` | public | |
| POST | `/categories` | admin | |
| GET | `/products` | public | filter, search, sort, paginate |
| GET | `/products/{id}` | public | |
| POST | `/products` | seller/admin | |
| PUT | `/products/{id}` | owner/admin | no stock edits — use inventory adjust |
| DELETE | `/products/{id}` | owner/admin | soft delete |
| POST | `/products/{id}/inventory/adjust` | owner/admin | `delta` ±, writes movement row |
| POST | `/orders` | any auth | creates order, decrements stock, enqueues payment |
| GET | `/orders` | any auth | own orders; admin sees all |
| GET | `/orders/{id}` | owner/admin | |
| POST | `/orders/{id}/cancel` | owner/admin | restores stock, only pre-`SHIPPED` |
| GET | `/admin/analytics` | admin | revenue, top products, daily orders, etc. |
| GET | `/admin/users` | admin | |
| PATCH | `/admin/users/{id}/suspend` | admin | flips `is_active` |
| GET | `/admin/audit-logs` | admin | filterable |

## Auth

JWT bearer (HS256). Two token types: access (default 15 min) and refresh (default 14 d). Three roles: `customer` (default), `seller`, `admin`. RBAC enforced via `require_role(...)` dependency.

## Order lifecycle

```
PENDING → PAYMENT_PROCESSING → CONFIRMED → SHIPPED → DELIVERED
                                          ↘
                                          CANCELLED
```

Cancellation allowed from `PENDING`, `PAYMENT_PROCESSING`, or `CONFIRMED`. Once `SHIPPED`, cancellation is rejected with `422 invariant_violation`.

Stock decrement is atomic: `UPDATE products SET stock = stock - :qty WHERE id = :id AND stock >= :qty RETURNING stock`. Two concurrent orders for the last unit cannot both succeed — exactly one wins.

## Payments

`PaymentService.process` is invoked by the `process_payment` ARQ task right after order creation. Outcome is randomized per `PAYMENT_SUCCESS_RATE`. Each transition (`INITIATED → PROCESSING → SUCCESS|FAILED`) is persisted to `payment_events`. Failures raise `PaymentSimulationError` so ARQ retries up to `WorkerSettings.max_tries` with backoff. Success triggers an `order_confirmed` email notification; failure triggers `payment_failed`.

## Tests

Postgres + Redis must be reachable. The typical setup is "DB on docker, everything else on host":

```bash
# 1. Bring up Postgres + Redis (one-time, leave running)
docker compose up postgres redis -d

# 2. Create the test database (one-time)
docker compose exec postgres createdb -U shopflow shopflow_test

# 3. Run
uv run pytest
uv run pytest tests/services/test_inventory.py -k race    # concurrency race
uv run pytest --cov=app                                    # with coverage
```

`.env` points `DATABASE_URL` / `TEST_DATABASE_URL` / `REDIS_URL` at `localhost` (docker publishes 5432 and 6379 to the host). The compose `api`, `worker`, and `migrate` services override these to use service names — that's why `docker compose up --build` still works without editing `.env`.

The session-scope conftest fixture runs `alembic upgrade head` against the test database, after wiping the public schema. So tests exercise the **same migration graph** the production stack uses. Each test then runs inside an outer transaction rolled back at teardown — the schema persists across the session, only data is reset.

ARQ tasks are tested by calling the task function directly — no live worker or Redis needed.

### Migrations workflow

```bash
# After changing a model, autogenerate a new revision
uv run alembic revision --autogenerate -m "describe change"

# Inspect — autogenerate misses enum changes and some server defaults; hand-edit if needed
$EDITOR alembic/versions/000X_*.py

# Apply
uv run alembic upgrade head
```

## Code quality

```bash
uv run ruff check .
uv run ruff format .
uv run ty check app
```

## Architecture

```
              ┌──────────┐
              │  Client  │
              └────┬─────┘
                   │ HTTPS
              ┌────▼─────┐         ┌────────────────┐
              │ FastAPI  │─────────┤ /docs (Swagger)
              │   API    │
              └────┬─────┘
                   │ AsyncSession (asyncpg)
              ┌────▼─────┐
              │ Postgres │
              └────▲─────┘
                   │ AsyncSession
              ┌────┴─────┐         ┌─────────┐
              │   ARQ    │◄────────┤  Redis  │
              │  Worker  │ jobs    └─────────┘
              └──────────┘
```

## ER diagram

```mermaid
erDiagram
    USERS ||--o{ ORDERS : "places"
    USERS ||--o{ PRODUCTS : "sells"
    USERS ||--o{ AUDIT_LOGS : "actor"
    USERS ||--o{ NOTIFICATIONS : "recipient"
    CATEGORIES ||--o{ PRODUCTS : "categorizes"
    PRODUCTS ||--o{ INVENTORY_MOVEMENTS : "tracks"
    PRODUCTS ||--o{ ORDER_ITEMS : "in"
    ORDERS ||--|{ ORDER_ITEMS : "contains"
    ORDERS ||--|| PAYMENTS : "settled by"
    PAYMENTS ||--o{ PAYMENT_EVENTS : "transitions"
```

## Postman

OpenAPI is the source of truth. Export a Postman v2.1 collection:

```bash
uv run python scripts/export_postman.py > shopflow.postman.json
```

Import in Postman: `File → Import → shopflow.postman.json`.

## Known gaps

- ARQ pool not yet in FastAPI lifespan — `enqueue` opens a fresh pool per call (fine for now, hot path later).
- Payment terminal failure (after max retries) does not auto-cancel the order or restore stock yet.
- Low-stock notification is logger-only; seller lookup + enqueue not wired.
- `AuditMiddleware` records request-id + access logs but does not auto-write `audit_logs` rows — call `AuditService.record(...)` from services for explicit business events.
