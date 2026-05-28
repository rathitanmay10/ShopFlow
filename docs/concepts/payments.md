# Payments

## Why it's a worker

Payment is the slow, lossy, retryable bit of order checkout. Putting it on ARQ means:

- API returns fast (order created, payment in-flight).
- Retries are free — ARQ handles backoff.
- Simulated provider failure doesn't 500 the client.

## The simulation

`PaymentService.process` in `app/services/payment.py`. Random outcome controlled by `PAYMENT_SUCCESS_RATE` (default 0.8 = 80% success).

Each call:

1. Load the order. If missing → `NotFoundError`. If status ≠ `PAYMENT_PROCESSING` → `InvariantViolationError` (stale queue entry, e.g. cancelled between enqueue and process).
2. `get_or_create_for_order(order)` — fetches the `Payment` row or inserts it with `status=INITIATED`.
3. Append `PaymentEvent(from=…, to=PROCESSING)`. Set payment `status=PROCESSING`, increment `attempts`.
4. Roll the dice.

### Success path

- Append `PaymentEvent(to=SUCCESS)`.
- `assert_transition(order.status, CONFIRMED)` → set order to `CONFIRMED`.
- Set payment `external_txn_id` to a fake token.
- Enqueue `send_notification(user_id, EMAIL, "order_confirmed", payload)`.

### Failure path (non-terminal)

- Append `PaymentEvent(to=FAILED, reason=...)`.
- Reset order to `PENDING` (so the next retry can re-transition).
- Raise `PaymentSimulationError` so ARQ retries with backoff (up to `WorkerSettings.max_tries = 4`).

### Failure path (terminal, after max retries)

`process_payment` in `app/workers/tasks.py` detects the terminal attempt via `ctx["job_try"] >= WorkerSettings.max_tries`. On terminal failure:

1. Commit the FAILED `PaymentEvent` + `attempts` increment + order `PENDING` reset (so the audit trail survives).
2. Open a fresh session and call `OrderService.system_cancel(order_id)` — that path restores stock for every line item via `InventoryService.restore` (`reason=CANCEL`, `actor_id=None`) and transitions the order to `CANCELLED`.
3. Commit and log `payment_terminal_cancel`.

The `payment_failed` email notification is already enqueued by the service on every failed attempt — including the terminal one — so the customer is informed without a separate terminal-only branch.

Net effect: terminal payment failure leaves the order `CANCELLED`, stock restored, payment row at `FAILED` with the full event history, and the customer notified.

## Terminal errors (no retry)

`NotFoundError` and `InvariantViolationError` raised from `process` are caught in `app/workers/tasks.py::process_payment` and logged at warning level — **without** re-raising. ARQ does not retry. These indicate stale queue entries: e.g. the order was already cancelled or the DB was reset between enqueue and process. Retrying would never succeed.

`PaymentSimulationError` is the **retryable** terminal: it propagates back to ARQ on every attempt except the last one. On the final attempt, the worker swallows it after running the system-cancel path described above, so ARQ doesn't log a spurious "task failed" stack trace for a state the system has already cleaned up.

## Event log

Every status transition is appended to `payment_events`:

| Field | Meaning |
|---|---|
| `from_status` | Previous payment status (NULL on first event) |
| `to_status` | New status |
| `reason` | Free-text (failure reason, etc.) |
| `created_at` | Auto-stamp |

This is the audit trail surfaced via `GET /payments/by-order/{order_id}`. `PaymentRepository.get_by_order_id` eagerly loads `events` via `selectinload`.

## Concurrency note

Only one ARQ worker dequeues a given job at a time (ARQ's contract). But if you scale horizontally and re-enqueue manually, the unique constraint on `payments.order_id` prevents two `Payment` rows for the same order.
