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

ARQ exhausts retries → task no longer re-enqueued. The failure branch in the service already enqueued `send_notification(user_id, EMAIL, "payment_failed", ...)` before raising on the final attempt. The order is left in `PENDING`. **It is not auto-cancelled and stock is not auto-restored** — that's an open gap.

## Terminal errors (no retry)

`NotFoundError` and `InvariantViolationError` raised from `process` are caught in `app/workers/tasks.py::process_payment` and logged at warning level — **without** re-raising. ARQ does not retry. These indicate stale queue entries: e.g. the order was cancelled or the DB was reset between enqueue and process. Retrying would never succeed.

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
