# Testing

## Setup (one-time)

```bash
# 1. Bring up Postgres + Redis (leave running)
docker compose up postgres redis -d

# 2. Create the test database
docker compose exec postgres createdb -U shopflow shopflow_test
```

`.env` points `DATABASE_URL` / `TEST_DATABASE_URL` / `REDIS_URL` at `localhost` (docker publishes 5432 and 6379 to host). The compose `api` / `worker` / `migrate` services override these to use service names — `docker compose up --build` still works without editing `.env`.

## Running

```bash
uv run pytest                                          # full suite
uv run pytest tests/api/test_orders.py                 # one file
uv run pytest tests/api/test_orders.py::test_cancel    # one test
uv run pytest -k race -x                               # concurrency race only, fail-fast
uv run pytest --cov=app                                # with coverage
```

## How isolation works

`pytest_configure` (sync, runs once before any tests, via subprocess):

```
DROP SCHEMA public CASCADE
CREATE SCHEMA public
alembic upgrade head
```

So tests exercise the **same migration graph** production uses — not an ORM-generated `metadata.create_all`. If a migration is broken, the suite refuses to even start.

Per-test:

- Fresh `AsyncEngine`.
- `AsyncSession(join_transaction_mode="create_savepoint")` — application-side `session.commit()` calls release a savepoint, and the outer transaction rolls back at teardown.
- Schema persists across the run; data is reset per test.

Net effect: tests can call real `session.commit()` and still get isolation. Trade-off: ~30–50 ms overhead per test from spinning up a new engine. Acceptable while the suite is small.

## Fixtures

| Fixture | What |
|---|---|
| `session` | Transactional `AsyncSession` |
| `client` | `httpx.AsyncClient` wired into the FastAPI app with the session injected via `dependency_overrides` |
| `customer`, `seller`, `admin` | Pre-made users of each role |
| `auth_headers(user)` | Returns `{"Authorization": "Bearer ..."}` for a given user |

Use `_make_user(session, role=...)` from `tests/conftest.py` instead of inlining `User(...)` blocks.

## Email validation gotcha

`email-validator` 2.x rejects RFC 6761 special-use TLDs (`.local`, `.test`, `.example`) — but `@example.com` is allow-listed. Use that in tests.

## Redis

Falls **open** when unreachable, so most tests don't need Redis running. Only tests that explicitly assert rate-limit / login-throttle behavior need it.

## ARQ task tests

Call the task function directly — **never** spin up a real worker.

Critical: `app.db.async_session_maker` is built at module import time using `get_settings().database_url` (prod DB). Tasks call it directly, so without patching, the test session and the task's session point at different databases.

Pattern:

```python
async def test_process_payment_success(session, ...):
    # ... seed data via `session` ...

    factory = _test_session_factory()  # built from TEST_DATABASE_URL
    with patch("app.workers.tasks.async_session_maker", factory):
        await process_payment({}, str(order_id))

    # ... assertions using `session` ...
```

Without the patch you'll see `ForeignKeyViolation` (task can't find rows the test seeded) and `RuntimeError: Event loop is closed` (task's session outlives the test).

See `tests/workers/test_tasks.py` for the full setup.

## What's NOT tested (yet)

- End-to-end with a live worker process (we call task functions directly).
- Multi-tenant isolation under load.
- Migration downgrade paths.
