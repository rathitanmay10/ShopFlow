# Inventory

## The invariant

Stock never goes negative. Two concurrent orders for the last unit cannot both succeed.

## The mechanism

Every stock mutation lives in `InventoryService`. Decrements use a single atomic SQL statement:

```sql
UPDATE products
SET stock = stock - :qty
WHERE id = :id
  AND deleted_at IS NULL
  AND stock_quantity >= :qty
RETURNING stock
```

If `0` rows return, `InventoryService.decrement` raises `InvariantViolationError("insufficient_stock")` → HTTP `422`.

Each call also inserts a row into `inventory_movements` with `reason ∈ {ORDER, ADJUST, CANCEL, RESTOCK, DAMAGE}`.

## What you must never do

- **Never** read stock, then check it in Python, then write. The `WHERE stock_quantity >= :qty` guard is the whole point.
- **Never** mutate `stock_quantity` outside `InventoryService`. The schema-layer enforcement is that `ProductUpdate` has no `stock_quantity` field — so `PUT /products/{id}` can't touch it.
- **Never** `asyncio.gather` over an order's items to parallelize decrements. `AsyncSession` is not concurrency-safe — corruption results. Loops stay sequential.

## Movement reasons

| Reason | Source |
|---|---|
| `ORDER` | `POST /orders` → decrement |
| `CANCEL` | `POST /orders/{id}/cancel` → restore (positive movement) |
| `ADJUST` | `POST /products/{id}/inventory/adjust` (manual ±) |
| `RESTOCK` | Manual ± via adjust with positive delta |
| `DAMAGE` | Manual − via adjust |

## Concurrency test

`tests/services/test_inventory.py::test_concurrent_decrement_on_last_unit` spawns two coroutines racing for the same final unit. Exactly one wins; the other raises `InvariantViolationError`. Touching the decrement path means re-running:

```bash
uv run pytest -k race -x
```

## Low-stock signal

When stock drops below `LOW_STOCK_THRESHOLD` (default 5), `InventoryService._maybe_emit_low_stock` fires after the decrement:

1. Logs `low_stock` at warning level with product id, current quantity, threshold, seller id.
2. Looks up `Product.seller_id` (single indexed SELECT).
3. Enqueues `send_notification(seller_id, "in_app", "low_stock", payload)` via ARQ. Uses the FastAPI lifespan pool when available, otherwise creates a fresh pool for the call.

The enqueue fires inside the decrement's DB transaction. If the transaction later rolls back, the notification stays queued — a transactional-outbox pattern would fix this, but for `low_stock` (advisory, low stakes) the trade-off is acceptable.

If the enqueue itself can't reach Redis, it logs a warning and returns — never fails the order.
