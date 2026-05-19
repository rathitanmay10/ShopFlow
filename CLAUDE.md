# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**ShopFlow** — event-driven e-commerce backend. Manages products, inventory, orders, payments, notifications, audit logs. Fully-async FastAPI API; async ARQ workers; PostgreSQL; Redis.

All modules below are implemented. Follow existing patterns. The full README (architecture diagrams, ER diagram, endpoint table, env table) is in `README.md`.

## Stack

- **Runtime**: Python 3.13 (`.python-version`), FastAPI, Uvicorn.
- **Package manager**: `uv` (lockfile `uv.lock`, manifest `pyproject.toml`). Do **not** use pip/poetry/pip-tools directly.
- **Dependency pinning policy**: do **not** blindly grab "latest". Before adding/upgrading a package, check its release notes for breaking changes, deprecations, and CVE advisories. Pin to a known-good version with an upper bound (e.g. `"fastapi>=0.136,<0.138"`) rather than open-ended `>=`. `uv.lock` is the source of truth and must be committed. Upgrades happen via deliberate `uv lock --upgrade-package <name>` — never `uv lock --upgrade` wholesale without reviewing the diff. Treat security advisories (`uv pip audit` or equivalent) as blocking before merging dep changes.
- **DB**: PostgreSQL via SQLAlchemy 2.x — **async only**. `asyncpg` driver + `AsyncSession` everywhere (API and workers). Single engine + session factory in `app/db/`. No sync `Session`.
- **Migrations**: Alembic. Async engine via `run_sync` in `env.py`. Migrations 0001..0007 already in tree.
- **Auth**: JWT bearer (access + refresh, HS256). Direct `bcrypt` lib (not passlib). RBAC roles: `customer`, `seller`, `admin`.
- **Background**: ARQ (async Redis queue). Worker is its own asyncio process; reuses `app.db.async_session_maker`. Worker module imports models/services, **never** the FastAPI `app` object. Two registered tasks: `process_payment(order_id)` and `send_notification(user_id, channel, event_type, payload)`.
- **Config**: `pydantic-settings` BaseSettings, loaded from `.env`. All config flows through `get_settings()` singleton in `app/core/config.py`.
- **Tooling**: `ruff` (lint + format), `ty` (typecheck), `pytest` + `pytest-asyncio` + `httpx.AsyncClient`, `pre-commit`.

## Architecture — strict layering

```
app/api  →  app/services  →  app/repositories  →  app/db (SQLAlchemy)
                                   ↑
                          app/models, app/schemas
```

Rules:

- **`app/api/`** — routers only. Parse request, call a service, commit if mutating, return a schema. **No `select`, `update`, `delete`, `selectinload` in routers.** If you need eager loading, add a repository method that returns the right shape. One router file per resource. Mount under `/api/v1`.
- **`app/services/`** — business rules, orchestration, cross-repository transactions. Receive `AsyncSession` via DI; do not open sessions themselves. Raise domain exceptions from `app/core/exceptions.py`; the API layer maps them to HTTP responses via `DomainError` handler in `app/main.py`.
- **`app/repositories/`** — all SQLAlchemy queries live here. One repository per aggregate root. Methods take a session + typed args, return ORM models. Repos never call other repos; services compose. For collections that the response schema iterates (e.g. `Order.items`), use `.options(selectinload(...))` in the repo query — relying on `lazy="selectin"` + `session.refresh(attribute_names=[...])` is unreliable in async mode.
- **`app/models/`** — SQLAlchemy ORM (`DeclarativeBase`, `Mapped[...]`).
- **`app/schemas/`** — Pydantic v2 request/response DTOs. Never reuse ORM models on the wire.
- **`app/workers/`** — ARQ tasks (`async def`). `tasks.py` registers `WorkerSettings`; `queue.py` provides `enqueue(settings, task_name, *args)` for fire-from-API. Tasks open a fresh `async_session_maker()` per invocation. Idempotent where possible.
- **`app/middleware/`** — `request_context.py` (assigns request-id, emits access log) and `rate_limit.py` (per-IP fixed-window via Redis, falls open if Redis unreachable).
- **`app/core/`** — `config.py` (Settings), `security.py` (JWT, bcrypt, `subject_uuid`), `exceptions.py` (`DomainError` hierarchy), `logging.py` (JSON formatter), `redis_client.py` (`get_redis_or_none` shared lazy-connect helper for rate limit / login throttle / etc).
- **`app/db/`** — async engine, `async_session_maker`, `Base`, `get_async_session` DI provider.
- **`app/utils/`** — pure, dependency-free helpers only. If it touches the DB or HTTP, it belongs in a service.
- **`app/main.py`** — app factory: configure logging, mount routers, add middleware, register `DomainError` handler. Keep thin.

### Cross-cutting concerns

- **Concurrency-safe inventory**: stock decrement uses atomic `UPDATE products SET stock = stock - :qty WHERE id = :id AND deleted_at IS NULL AND stock_quantity >= :qty RETURNING ...`. If 0 rows returned, raise `InvariantViolationError("insufficient_stock")`. Each call also inserts a row into `inventory_movements`. Never read-then-write stock across two statements. Every stock mutation lives in `InventoryService` — products router has no `stock_quantity` field in `ProductUpdate`.
- **Order lifecycle**: `PENDING → PAYMENT_PROCESSING → CONFIRMED → SHIPPED → DELIVERED`, plus `CANCELLED` reachable from `{PENDING, PAYMENT_PROCESSING, CONFIRMED}`. State transitions are enforced by `assert_transition` and `CANCELLABLE` in `app/services/order_state.py` — not free-form strings.
- **Payment simulation**: `PaymentService.process` in `app/services/payment.py`. Random success rate from `PAYMENT_SUCCESS_RATE`. Persists every transition to `payment_events`. Failures raise `PaymentSimulationError` so ARQ retries (`max_tries` on `WorkerSettings`). Success enqueues `send_notification` for `order_confirmed`; failure enqueues `payment_failed`.
- **Audit log**: `AuditService.record(...)` is the explicit-event writer; call it from services for business events (login, suspension, etc). `RequestContextMiddleware` only emits a request-id header + access log — it does not auto-write `audit_logs` rows.
- **Auth dependencies**: `get_current_user`, `require_role(*roles)`, `SessionDep`, `SettingsDep`, `CurrentUserDep` in `app/api/deps.py`. Routers depend on these — never decode JWT inside a router body. UUID extraction from token payloads uses `subject_uuid(payload)` from `app/core/security.py`, not ad-hoc `UUID(payload["sub"])` + try/except.

### Postgres enum mapping (load-bearing)

Every `Enum(SomeStrEnum, name="...")` column **must** include `values_callable=lambda e: [m.value for m in e]`. Without it, SQLAlchemy serializes the enum **name** (`"CUSTOMER"`) but Alembic created the type with the **value** (`"customer"`), so inserts fail with `invalid input value for enum`. Convention applies to every model: User.role, Product.status, InventoryMovement.reason, Order.status, Payment.status (and PaymentEvent's two columns referencing it), Notification.channel + status.

## Commands

```bash
# install / sync deps
uv sync

# add / remove deps (regenerates uv.lock)
uv add "<pkg>>=X.Y,<X.Z"
uv add --dev "<pkg>>=X.Y,<X.Z"

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
uv run pytest tests/api/test_orders.py::test_cancel_restores_stock
uv run pytest -k race -x                       # concurrency race only
uv run pytest --cov=app                        # with coverage

# docker (DB-only is the common workflow; full stack on demand)
docker compose up postgres redis -d
docker compose up --build
```

## Tests

- Test DB is `shopflow_test`. Create once: `docker compose exec postgres createdb -U shopflow shopflow_test`.
- `tests/conftest.py` runs **once at pytest startup** (via `pytest_configure`, sync): `DROP SCHEMA public CASCADE` → `CREATE SCHEMA public` → `alembic upgrade head` via subprocess. So tests exercise the **same migration graph** production uses, not `metadata.create_all`.
- Each test gets a fresh `AsyncEngine` and an `AsyncSession` with `join_transaction_mode="create_savepoint"`. Application-side `session.commit()` releases a savepoint; the outer transaction rolls back at teardown. Schema persists across the session, data is reset per test.
- Fixtures: `session`, `client` (`httpx.AsyncClient` with the session injected via `dependency_overrides`), `customer`, `seller`, `admin`, `auth_headers(user) -> dict`. Use `_make_user(session, role=...)` from conftest instead of inlining `User(...)` blocks.
- Redis-backed helpers (rate limit, login throttle, ARQ `enqueue`) fall open when Redis is unreachable, so most tests don't need Redis running.
- ARQ task tests call the task function directly; never spin up a real worker.
- Emails in tests must use real-looking domains (`@example.com`). `email-validator` 2.x rejects RFC 6761 special-use TLDs like `.local`, `.test`, `.example`.

## Conventions

- **Fully async.** API path and workers both `async def` with `AsyncSession`. No sync DB driver, no `Session`, no threadpool DB calls. Blocking lib → Asyncer's `asyncify` (see `.claude/skills/fastapi/`).
- **`AsyncSession` is NOT concurrency-safe.** Never `asyncio.gather` operations that share a session — SQLAlchemy docs prohibit it; corruption results. Loops over an order's items decrementing stock stay sequential.
- **`Annotated` style everywhere.** Path/Query/Header/Body params and `Depends(...)` go inside `Annotated[...]`, not as default values. Create reusable dep aliases (`CurrentUserDep`, `SessionDep`, `SettingsDep`). No `...` (Ellipsis). No Pydantic `RootModel`. No `ORJSONResponse`/`UJSONResponse` — return types let Pydantic serialize.
- **Routers own their prefix/tags.** `APIRouter(prefix="/products", tags=["products"])`, not args to `include_router`. Shared auth via router-level `dependencies=[Depends(require_role(...))]`.
- **One HTTP method per function.** No `@app.api_route(methods=[...])`.
- **Dependency injection over imports** for sessions, current user, settings. Makes tests trivial.
- **Pydantic v2 only.** `model_config = ConfigDict(from_attributes=True)` for ORM→schema; `.model_dump()` not `.dict()`.
- **SQLAlchemy 2.x style only.** `select(...)`, `Mapped[...]`, `mapped_column(...)`, `session.scalar(...)`. No legacy `Query` API.
- **Soft delete** for products via `deleted_at` timestamp + a default `_base()` filter helper in the repo. Don't sprinkle `WHERE deleted_at IS NULL` in services.
- **No business logic in Alembic migrations.** Data backfills go in a separate one-shot script under `scripts/` or a service method, invoked manually.
- **Errors at boundaries**: services raise typed `DomainError` subclasses; the global handler in `main.py` maps them to HTTP responses with `{error: {code, message, metadata}}`. Routers do not build error responses inline.
- **Eager-load for serialization**: if a Pydantic response schema iterates a relationship, the repository query must `selectinload` it. See `OrderRepository.get` / `list_`.
- **Streaming**: JSON Lines via `AsyncIterable[Model]` return type; SSE via `response_class=EventSourceResponse`; bytes via `response_class=` subclass of `StreamingResponse` + `yield`. See `.claude/skills/fastapi/references/streaming.md`.

## Things to verify before claiming a task done

- New endpoint: router + service + repo + schema + test + migration (if model touched).
- Touching inventory or order state: transactional path preserved; concurrency test still passes (`tests/services/test_inventory.py::test_concurrent_decrement_on_last_unit`).
- New env var: added to `Settings`, documented in `.env.example` + README env table, threaded through DI — not read via `os.environ` ad-hoc.
- New model field: Alembic autogenerate run, migration reviewed (autogenerate misses enum changes, server defaults, and some FK options).
- New enum column: `values_callable=lambda e: [m.value for m in e]` set on the `Enum(...)` call.
- New ARQ task: registered in `WorkerSettings.functions`; enqueue site uses string task name matching the function `__name__`.
- New / upgraded dependency: pinned version chosen from release notes (not "latest"), upper bound set in `pyproject.toml`, `uv.lock` regenerated and committed, advisory scan clean.
- New service that needs Redis: use `app.core.redis_client.get_redis_or_none(url, ctx=...)` for lazy-connect semantics; don't duplicate `Redis.from_url + ping + warn + None`.
