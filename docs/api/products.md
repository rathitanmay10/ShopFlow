# Product + inventory endpoints

## `GET /api/v1/products`

Public. Query params:

| Param | Type | Notes |
|---|---|---|
| `q` | str | text search (name) |
| `category_id` | UUID | filter |
| `min_price`, `max_price` | decimal | filter |
| `status` | `active` \| `out_of_stock` \| `discontinued` | filter |
| `sort` | `newest` \| `oldest` \| `price_asc` \| `price_desc` | default `newest` |
| `page`, `page_size` | int | pagination |

Soft-deleted products (with `deleted_at` set) are filtered out by `ProductRepository._base()`.

## `GET /api/v1/products/{id}`

Public.

## `POST /api/v1/products`

`seller` or `admin`. Stock is set on creation. After that, **never** edit `stock_quantity` via `PUT` — use inventory adjust.

## `PUT /api/v1/products/{id}`

Owner (seller who created it) or admin. `ProductUpdate` schema has **no** `stock_quantity` field — that's enforced at the schema layer.

## `DELETE /api/v1/products/{id}`

Owner or admin. Soft delete only — sets `deleted_at = now()`. Row remains for FK integrity with historical orders.

## `POST /api/v1/products/{id}/inventory/adjust`

Owner or admin. Body: `{delta, reason}`. Positive `delta` restocks; negative draws down (e.g. damage). Writes a row to `inventory_movements`.

Every stock mutation lives in `InventoryService` — see [Inventory concurrency](../concepts/inventory.md) for the atomic-decrement guarantee.

## Concurrency

Stock decrement uses:

```sql
UPDATE products
SET stock = stock - :qty
WHERE id = :id AND deleted_at IS NULL AND stock_quantity >= :qty
RETURNING stock
```

If 0 rows returned, raises `InvariantViolationError("insufficient_stock")` → `422`. Two concurrent orders for the last unit cannot both succeed — exactly one wins.
