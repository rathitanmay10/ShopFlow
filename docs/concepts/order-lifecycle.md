# Order lifecycle

## States

```
PENDING → PAYMENT_PROCESSING → CONFIRMED → SHIPPED → DELIVERED
   │              │                 │
   └──────────────┴─────────────────┘
                  ▼
              CANCELLED
```

| State | Meaning |
|---|---|
| `PENDING` | Order row inserted; stock not yet decremented (very brief; immediately transitions) |
| `PAYMENT_PROCESSING` | Stock decremented, payment task enqueued, awaiting worker |
| `CONFIRMED` | Payment succeeded |
| `SHIPPED` | Manual transition (not currently exposed via HTTP) |
| `DELIVERED` | Manual transition |
| `CANCELLED` | Stock restored; terminal |

## Allowed transitions

Defined in `app/services/order_state.py` and enforced by `assert_transition(from_state, to_state)`. Not free-form strings.

```python
TRANSITIONS = {
    PENDING:            {PAYMENT_PROCESSING, CANCELLED},
    PAYMENT_PROCESSING: {CONFIRMED, PENDING, CANCELLED},  # PENDING is the retry path
    CONFIRMED:          {SHIPPED, CANCELLED},
    SHIPPED:            {DELIVERED},
    DELIVERED:          set(),
    CANCELLED:          set(),
}

CANCELLABLE = {PENDING, PAYMENT_PROCESSING, CONFIRMED}
```

Any other transition raises a domain exception.

## Retry path: `PAYMENT_PROCESSING → PENDING`

On payment failure (before exhausting retries), the worker re-sets the order to `PENDING` so that the next retry can re-transition `PENDING → PAYMENT_PROCESSING` cleanly. Without this, the assertion in `assert_transition` would reject the retry.

## Cancellation

`POST /orders/{id}/cancel`:

1. Verify caller is owner or admin.
2. Verify `order.status ∈ CANCELLABLE`. Else `422 order_not_cancellable`.
3. For each `OrderItem`: `InventoryService.restore(...)` with `reason=CANCEL`.
4. `assert_transition(current, CANCELLED)` → set status.
5. Commit.

Already-`SHIPPED` or `DELIVERED` orders cannot be cancelled via this endpoint.

## What does NOT happen

- There's no scheduled "expire pending orders" sweep.
- `SHIPPED` / `DELIVERED` transitions are not exposed via HTTP yet.

## System cancellation

`OrderService.system_cancel(order_id)` performs the same flow as customer-initiated `cancel(order_id, actor)` — verify `CANCELLABLE`, restore stock per line item, transition to `CANCELLED` — but **without** an actor permission check or audit-trail actor id. It's used by the payment worker on terminal failure (see [Payments](payments.md)) and is never exposed over HTTP.
