# Payment endpoints

## `GET /api/v1/payments/by-order/{order_id}`

Owner of the order or admin. Returns:

```json
{
  "id": "uuid",
  "order_id": "uuid",
  "amount": "19.98",
  "currency": "USD",
  "status": "success",
  "attempts": 1,
  "external_txn_id": "...",
  "created_at": "...",
  "updated_at": "...",
  "events": [
    {"from_status": null,        "to_status": "initiated",  "created_at": "..."},
    {"from_status": "initiated", "to_status": "processing", "created_at": "..."},
    {"from_status": "processing","to_status": "success",    "created_at": "..."}
  ]
}
```

Errors:

| Code | Meaning |
|---|---|
| `401` | Not authenticated |
| `403 not_order_owner` | Order belongs to someone else and caller is not admin |
| `404 order_not_found` | Order doesn't exist |
| `404 payment_not_found` | Order exists but worker hasn't created a `Payment` row yet (very early after order creation) |

## How payments work

Payment processing is **not synchronous** with order creation. When `POST /orders` returns, the order is `PAYMENT_PROCESSING` and `process_payment(order_id)` is enqueued on ARQ. The worker:

1. Loads the order.
2. Gets or creates the `Payment` row.
3. Randomly succeeds or fails per `PAYMENT_SUCCESS_RATE` (default 0.8).
4. On success: order → `CONFIRMED`, payment → `SUCCESS`, enqueues `send_notification(order_confirmed)`.
5. On failure: order → `PENDING` (so next retry can re-transition), payment → `FAILED`, raises `PaymentSimulationError` so ARQ retries (`max_tries=4` with backoff). After max retries: failure-path enqueues `send_notification(payment_failed)`.

Every status transition is appended to `payment_events`. See [Payments concept](../concepts/payments.md) for retry behavior and terminal errors.
