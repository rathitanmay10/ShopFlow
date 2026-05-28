# Workers (ARQ)

## Running

```bash
uv run arq app.workers.tasks.WorkerSettings
```

The worker is its own asyncio process. It reuses `app.db.async_session_maker` from `app/db/` but **never** imports the FastAPI `app` object — keeps the worker decoupled from HTTP startup.

## Tasks

| Name | Args | Triggered by |
|---|---|---|
| `process_payment` | `order_id: str` | `POST /orders` (right after commit) |
| `send_notification` | `user_id, channel, event_type, payload` | `PaymentService.process` on success / failure |

Both registered in `WorkerSettings.functions`.

## Worker session lifecycle

Each task **opens its own session** with `async_session_maker()`:

```python
async def process_payment(ctx, order_id: str) -> None:
    async with async_session_maker() as session:
        try:
            await PaymentService(session, settings).process(UUID(order_id))
            await session.commit()
        except PaymentSimulationError:
            await session.rollback()
            raise  # let ARQ retry
        except (NotFoundError, InvariantViolationError) as exc:
            log.warning(...)
            # terminal — don't re-raise, no retry
```

Why a fresh session per call:

- Tasks may run in parallel under the worker — sharing a session would corrupt state.
- A task's session lifetime is the task lifetime — no leaks across jobs.

## Retries

`WorkerSettings.max_tries = 4`. ARQ applies exponential backoff between attempts.

Re-raise the exception to retry. Catch + log (no re-raise) to mark terminal.

| Exception | Re-raise? | Why |
|---|---|---|
| `PaymentSimulationError` | yes | Simulated provider failure — try again |
| `NotFoundError` | no | Order doesn't exist (stale enqueue) — retry would still fail |
| `InvariantViolationError` | no | Order in wrong state (e.g. already cancelled) — retry would still fail |

## Enqueueing from API

```python
from app.workers.queue import enqueue
from app.api.deps import ArqPoolDep

@router.post("")
async def create_order(..., pool: ArqPoolDep) -> OrderRead:
    ...
    await enqueue(settings, "process_payment", str(order.id), pool=pool)
```

`enqueue` accepts a `pool=` kwarg:

- If a pool is passed, it reuses it. The FastAPI `lifespan` in `app/main.py` creates one ARQ pool on startup, stores it in `app.state.arq_pool`, and closes it on shutdown. `ArqPoolDep` reads from `app.state` and injects it into routers. **This is the hot path** — single TCP connection shared across all requests.
- If no pool is passed (worker that didn't pick it up, or lifespan failed), `enqueue` falls back to `create_pool(...) → enqueue → aclose()`. Slower, but resilient.
- If Redis is unreachable on either path, `enqueue` logs a warning and returns `False` — **fails open**.

## Enqueueing from a worker task

ARQ provides its own `ArqRedis` pool to running tasks via `ctx["redis"]`. Pass it through:

```python
async def process_payment(ctx, order_id):
    settings = ctx["settings"]
    arq_pool = ctx.get("redis")
    async with async_session_maker() as session:
        await PaymentService(session, settings, arq_pool=arq_pool).process(UUID(order_id))
```

`PaymentService` then passes the pool down to its own `enqueue(...)` calls (for `order_confirmed` / `payment_failed` notifications) — no extra pool created.

## Testing tasks

Call task functions directly — never spin up a real worker. The session-maker import is module-level (`from app.db import async_session_maker`), so tests must patch it:

```python
with patch("app.workers.tasks.async_session_maker", test_session_factory):
    await process_payment(ctx, str(order_id))
```

Otherwise the task hits prod DB (where test data doesn't exist) → FK violations + event-loop leaks.

See [Testing](testing.md) for the full pattern.
