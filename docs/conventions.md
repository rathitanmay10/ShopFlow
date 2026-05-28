# Conventions

Rules that apply across every file. Most exist because of a concrete failure mode.

## Fully async

API path and workers are both `async def` with `AsyncSession`. No sync DB driver, no `Session`, no threadpool DB calls.

Blocking lib → wrap with Asyncer's `asyncify`.

## `AsyncSession` is NOT concurrency-safe

Never `asyncio.gather` operations that share a session — SQLAlchemy docs prohibit it; corruption results. Loops over an order's items decrementing stock stay sequential.

## FastAPI style

- `Annotated` everywhere. Path/Query/Header/Body params and `Depends(...)` go inside `Annotated[...]`, not as default values.
- Reusable dep aliases: `CurrentUserDep`, `SessionDep`, `SettingsDep`.
- No `...` (Ellipsis). No `RootModel`. No `ORJSONResponse` / `UJSONResponse` — return-type annotations let Pydantic serialize.
- Routers own their prefix/tags: `APIRouter(prefix="/products", tags=["products"])` — not args to `include_router`.
- One HTTP method per function. No `@app.api_route(methods=[...])`.
- Dependency injection over imports for sessions, current user, settings.

## Pydantic v2 only

`model_config = ConfigDict(from_attributes=True)` for ORM → schema. `.model_dump()` not `.dict()`. Schemas in routers serialize directly from ORM via the return-type annotation — no `Schema.model_validate(orm_obj)` in routers.

## SQLAlchemy 2.x style only

`select(...)`, `Mapped[...]`, `mapped_column(...)`, `session.scalar(...)`. No legacy `Query` API.

## Eager-load for serialization

If a Pydantic response schema iterates a relationship (e.g. `Order.items`, `Payment.events`), the **repository query** must `.options(selectinload(...))` it.

Relying on `lazy="selectin"` plus `session.refresh(attribute_names=[...])` is unreliable in async mode. Load in the repo, period.

## Postgres enum mapping

Every `Enum(SomeStrEnum, name="...")` column **must** include:

```python
values_callable=lambda e: [m.value for m in e]
```

Without it, SQLAlchemy serializes the enum **name** (`"CUSTOMER"`) but Alembic created the type with the **value** (`"customer"`), so inserts fail with `invalid input value for enum`.

Applies to: `User.role`, `Product.status`, `InventoryMovement.reason`, `Order.status`, `Payment.status` (and `PaymentEvent`'s two columns referencing it), `Notification.channel + status`.

## Soft delete

Products use a `deleted_at` timestamp + a default `_base()` filter in `ProductRepository`. Don't sprinkle `WHERE deleted_at IS NULL` in services.

## No business logic in Alembic migrations

Data backfills go in a separate one-shot script under `scripts/` or a service method, invoked manually.

## Errors at boundaries

Services raise typed `DomainError` subclasses; the global handler in `main.py` maps them to HTTP responses with `{error: {code, message, metadata}}`. Routers do not build error responses inline.

## Dependency pinning

Do **not** blindly grab "latest". Before adding/upgrading a package:

1. Check release notes for breaking changes, deprecations, CVE advisories.
2. Pin with an upper bound: `"fastapi>=0.136,<0.138"` — not open-ended `>=`.
3. `uv.lock` is the source of truth and must be committed.
4. Upgrades happen via deliberate `uv lock --upgrade-package <name>` — never `uv lock --upgrade` wholesale.
5. Advisory scan (`uv pip audit` or equivalent) is blocking before merging dep changes.

## Streaming

- JSON Lines via `AsyncIterable[Model]` return type.
- SSE via `response_class=EventSourceResponse`.
- Bytes via `response_class=` subclass of `StreamingResponse` + `yield`.

## Verification checklist before claiming done

- New endpoint: router + service + repo + schema + test + migration (if model touched).
- Inventory or order state: transactional path preserved; concurrency test still passes (`tests/services/test_inventory.py::test_concurrent_decrement_on_last_unit`).
- New env var: added to `Settings`, documented in `.env.example` + env table, threaded through DI — not read via `os.environ` ad-hoc.
- New model field: Alembic autogenerate run, migration reviewed (autogenerate misses enum changes, server defaults, and some FK options).
- New enum column: `values_callable=lambda e: [m.value for m in e]` set.
- New ARQ task: registered in `WorkerSettings.functions`; enqueue site uses string task name matching the function `__name__`.
- New / upgraded dep: pinned, upper bound set, `uv.lock` regenerated and committed, advisory scan clean.
- New service that needs Redis: use `app.core.redis_client.get_redis_or_none(url, ctx=...)` for lazy-connect.
