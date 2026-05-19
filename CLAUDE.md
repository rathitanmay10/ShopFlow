# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**ShopFlow** — event-driven e-commerce backend. Manages products, inventory, orders, payments, notifications. Fully-async FastAPI API; async ARQ workers; PostgreSQL; Redis.

Greenfield. Most modules not yet implemented — when adding code, follow the architecture below rather than inferring from existing files.

## Stack

- **Runtime**: Python 3.13 (`.python-version`), FastAPI, Uvicorn.
- **Package manager**: `uv` (lockfile `uv.lock`, manifest `pyproject.toml`). Do **not** use pip/poetry/pip-tools directly.
- **Dependency pinning policy**: do **not** blindly grab "latest". Before adding/upgrading a package, check its release notes for breaking changes, deprecations, and CVE advisories. Pin to a known-good version with an upper bound (e.g. `"fastapi>=0.136,<0.137"`) rather than open-ended `>=`. `uv.lock` is the source of truth and must be committed. Upgrades happen via deliberate `uv lock --upgrade-package <name>` — never `uv lock --upgrade` wholesale without reviewing the diff. Treat security advisories (`uv pip audit` or equivalent) as blocking before merging dep changes.
- **DB**: PostgreSQL via SQLAlchemy 2.x — **async only**. `asyncpg` driver + `AsyncSession` everywhere (API and workers). Single engine + session factory in `app/db/`. No sync `Session`.
- **Migrations**: Alembic. Configured for async engine (`run_sync` inside `env.py`).
- **Auth**: JWT bearer (access + refresh). RBAC roles: `customer`, `seller`, `admin`.
- **Background**: ARQ (async Redis queue). Worker is its own asyncio process; reuses the same `AsyncSession` factory as the API. Worker module imports models/services, **never** the FastAPI `app` object.
- **Config**: `pydantic-settings` BaseSettings, loaded from `.env`. All config flows through one `Settings` singleton in `app/core/config.py`.
- **Tooling**: `ruff` (lint + format), `ty` (typecheck), `pytest` + `pytest-asyncio` + `httpx.AsyncClient`, `pre-commit`.

## Architecture — strict layering

```
app/api  →  app/services  →  app/repositories  →  app/db (SQLAlchemy)
                                   ↑
                          app/models, app/schemas
```

Rules:

- **`app/api/`** — routers only. Parse request, call a service, return a schema. **No SQLAlchemy, no business logic.** One router file per resource (`products.py`, `orders.py`, …). Mount under versioned prefix (`/api/v1`).
- **`app/services/`** — business rules, orchestration, cross-repository transactions. Receive `AsyncSession` via DI; do not open sessions themselves. Raise domain exceptions (defined in `app/core/exceptions.py`); the API layer maps them to HTTP errors.
- **`app/repositories/`** — all SQLAlchemy queries live here. One repository per aggregate root. Methods take a session + typed args, return ORM models. Repos never call other repos; services compose.
- **`app/models/`** — SQLAlchemy ORM (`DeclarativeBase`, `Mapped[...]`).
- **`app/schemas/`** — Pydantic v2 request/response DTOs. Never reuse ORM models on the wire.
- **`app/workers/`** — ARQ tasks (`async def`). Use the shared `AsyncSession` factory; open a fresh session per task (don't carry one across enqueues). Idempotent where possible (payment retries, notifications). `WorkerSettings` lives here.
- **`app/middleware/`** — auth, rate limiting, request ID, audit logging.
- **`app/core/`** — `config.py`, `security.py` (JWT + password hashing), `exceptions.py`, `logging.py`.
- **`app/db/`** — async engine setup, session factory, DI provider (`get_async_session`), `Base`.
- **`app/utils/`** — pure, dependency-free helpers only. If it touches the DB or HTTP, it belongs in a service.
- **`app/main.py`** — app factory: create FastAPI, mount routers, add middleware, register exception handlers. Keep thin.

### Cross-cutting concerns

- **Concurrency-safe inventory**: stock decrement must use `SELECT ... FOR UPDATE` (or atomic `UPDATE ... WHERE stock >= :qty` returning affected rows) inside a single transaction with the order insert. Never read-then-write stock across two statements. Two simultaneous orders for the last unit must not produce negative stock.
- **Order lifecycle**: `PENDING → PAYMENT_PROCESSING → CONFIRMED → SHIPPED → DELIVERED`. Cancellation only valid pre-`SHIPPED`. State transitions live in the order service; enforce as enum + guard, not free-form strings.
- **Payment simulation**: synthetic gateway in `app/services/payment.py`. Random failures + ARQ retry task (`max_tries` on the task, exponential backoff). Persist every state change to `payments` + history table — don't mutate in place.
- **Audit log**: write via middleware or a service helper; never inside repositories. Captures actor, action, timestamp, metadata.
- **Auth dependencies**: define `get_current_user`, `require_role(...)` in `app/api/deps.py`. Routers depend on these — never decode JWT inside a router body.

## Commands

```bash
# install / sync deps
uv sync

# add / remove deps (edits pyproject.toml + uv.lock)
uv add fastapi "sqlalchemy[asyncio]" asyncpg alembic pydantic-settings arq redis "passlib[bcrypt]" "python-jose[cryptography]"
uv add --dev ruff ty pytest pytest-asyncio httpx pre-commit

# run dev server
uv run uvicorn app.main:app --reload

# alembic
uv run alembic revision --autogenerate -m "msg"
uv run alembic upgrade head

# arq worker
uv run arq app.workers.tasks.WorkerSettings

# lint / format / typecheck
uv run ruff check .
uv run ruff format .
uv run ty check app

# tests (user runs these — do NOT execute yourself; suggest the command)
uv run pytest
uv run pytest tests/api/test_orders.py::test_cancel_before_shipping
uv run pytest -k inventory -x

# docker
docker compose up --build
```

## Conventions

- **Fully async.** API path and workers both `async def` with `AsyncSession`. No sync DB driver, no `Session`, no threadpool DB calls. If a third-party lib is blocking, wrap with Asyncer's `asyncify` — do **not** sprinkle `def` handlers as workaround. See `.claude/skills/fastapi/SKILL.md` for the async/def rule and `references/other-tools.md` for Asyncer.
- **`Annotated` style everywhere.** Path/Query/Header/Body params and `Depends(...)` go inside `Annotated[...]`, not as default values. Create reusable dep aliases (`CurrentUserDep`, `SessionDep`, `SettingsDep`). No `...` (Ellipsis). No Pydantic `RootModel`. No `ORJSONResponse`/`UJSONResponse` — return types let Pydantic serialize.
- **Routers own their prefix/tags.** `APIRouter(prefix="/products", tags=["products"])`, not args to `include_router`. Shared auth via router-level `dependencies=[Depends(require_role(...))]`.
- **One HTTP method per function.** No `@app.api_route(methods=[...])`.
- **Dependency injection over imports** for sessions, current user, settings. Makes tests trivial.
- **Pydantic v2 only.** `model_config = ConfigDict(from_attributes=True)` for ORM→schema; `.model_dump()` not `.dict()`.
- **SQLAlchemy 2.x style only.** `select(...)`, `Mapped[...]`, `mapped_column(...)`. No legacy `Query` API.
- **Soft delete** for products via `deleted_at` timestamp + a default query filter helper in the repo. Don't sprinkle `WHERE deleted_at IS NULL` in services.
- **No business logic in Alembic migrations.** Data backfills go in a separate one-shot script under `scripts/` or a service method, invoked manually.
- **Tests**: API tests use `httpx.AsyncClient` against the app + a real Postgres test DB (transactional rollback per test). For ARQ tasks, call the task function directly in tests — never spin up a real worker or Redis.
- **Errors at boundaries**: services raise typed domain exceptions; a global handler in `main.py` maps them to HTTP responses. Routers do not build error responses inline.
- **Streaming**: JSON Lines via `AsyncIterable[Model]` return type; SSE via `response_class=EventSourceResponse`; bytes via `response_class=` subclass of `StreamingResponse` + `yield`. See `.claude/skills/fastapi/references/streaming.md`.

## Things to verify before claiming a task done

- New endpoint: router + service + repo + schema + test + migration (if model touched).
- Touching inventory or order state: confirm the transactional path is preserved; add or update a concurrency test.
- New env var: added to `Settings`, documented in `.env.example`, threaded through DI — not read via `os.environ` ad-hoc.
- New model field: Alembic autogenerate run, migration reviewed (autogenerate misses enum changes and server defaults).
- New / upgraded dependency: pinned version chosen from release notes (not "latest"), upper bound set in `pyproject.toml`, `uv.lock` regenerated and committed, advisory scan clean.
