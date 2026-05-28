# Order endpoints

## `POST /api/v1/orders`

Any authenticated user. Body:

```json
{
  "items": [
    {"product_id": "uuid", "quantity": 2}
  ]
}
```

Flow:

1. Load all products in the payload via `ProductRepository.get_many_by_ids`.
2. Reject if any are missing → `404 product_not_found`.
3. Reject if any are `DISCONTINUED` → `422 product_discontinued`.
4. Build `OrderItem` rows; total = `sum(unit_price * quantity)`.
5. Insert `Order(status=PENDING)` + flush.
6. For each line: atomic stock decrement via `InventoryService.decrement` (sequential — sessions are not concurrency-safe).
7. Transition `PENDING → PAYMENT_PROCESSING`.
8. Commit.
9. Enqueue `process_payment(order.id)` on ARQ.

Returns the order with `items` eagerly loaded.

## `GET /api/v1/orders`

Any authenticated user. Paginated. Customer sees own orders; admin sees all.

## `GET /api/v1/orders/{order_id}`

Owner or admin.

## `POST /api/v1/orders/{order_id}/cancel`

Owner or admin. Allowed only when status ∈ `{PENDING, PAYMENT_PROCESSING, CONFIRMED}` (see `CANCELLABLE` in `app/services/order_state.py`).

Restores stock for every line via `InventoryService.restore` with `reason=CANCEL`. Transitions order to `CANCELLED`.

Already-shipped orders return `422 order_not_cancellable`.

## Lifecycle

```
PENDING → PAYMENT_PROCESSING → CONFIRMED → SHIPPED → DELIVERED
   │              │                 │
   └──────────────┴─────────────────┘
                  ▼
              CANCELLED
```

State transitions are enforced by `assert_transition` — see [Order lifecycle](../concepts/order-lifecycle.md).
