# API overview

All endpoints under `/api/v1`. JSON in, JSON out. Errors carry `{error: {code, message, metadata}}`.

## Auth model

JWT bearer (HS256). Two token types: **access** (default 15 min) and **refresh** (default 14 d). Three roles: `customer` (default), `seller`, `admin`. RBAC enforced via `require_role(...)` dependency.

`Authorization: Bearer <access_token>` on every protected request.

### Testing in Swagger UI

1. Open <http://localhost:8000/docs>
2. Call `POST /api/v1/auth/login` with credentials → copy `access_token` from response.
3. Click **Authorize** (🔒) at top right → paste token → **Authorize**.
4. All subsequent requests include `Authorization: Bearer <token>`.

## Endpoint table

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/register` | public | creates user, default role `customer` |
| POST | `/auth/login` | public | returns access + refresh; throttled per IP+email |
| POST | `/auth/refresh` | public | rotates token pair |
| GET | `/categories` | public | |
| POST | `/categories` | admin | |
| GET | `/products` | public | filter, search, sort, paginate |
| GET | `/products/{id}` | public | |
| POST | `/products` | seller/admin | |
| PUT | `/products/{id}` | owner/admin | no stock edits — use inventory adjust |
| DELETE | `/products/{id}` | owner/admin | soft delete |
| POST | `/products/{id}/inventory/adjust` | owner/admin | `delta` ±, writes movement row |
| POST | `/orders` | any auth | creates order, decrements stock, enqueues payment |
| GET | `/orders` | any auth | own orders; admin sees all |
| GET | `/orders/{id}` | owner/admin | |
| POST | `/orders/{id}/cancel` | owner/admin | restores stock, only pre-`SHIPPED` |
| GET | `/payments/by-order/{order_id}` | owner/admin | Payment with status + events |
| GET | `/notifications` | any auth | own notifications, paginated |
| GET | `/admin/analytics` | admin | revenue, top products, daily orders |
| GET | `/admin/users` | admin | |
| PATCH | `/admin/users/{id}/suspend` | admin | flips `is_active` |
| GET | `/admin/audit-logs` | admin | filterable |

## Common error codes

| HTTP | `error.code` example | Cause |
|---|---|---|
| 400 | `validation_error` | Pydantic schema failure |
| 401 | `invalid_credentials`, `token_expired` | Auth |
| 403 | `not_order_owner`, `role_forbidden` | RBAC / ownership |
| 404 | `order_not_found`, `product_not_found` | Missing resource |
| 409 | `slug_taken`, `email_taken` | Unique constraint |
| 422 | `insufficient_stock`, `order_not_cancellable` | Business rule |
| 429 | `rate_limited` | Throttle |

## Pagination

All list endpoints take `page` (≥1) and `page_size` (1–100). Response shape:

```json
{
  "items": [...],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

## Endpoint pages

- [Auth](auth.md)
- [Products](products.md)
- [Orders](orders.md)
- [Payments](payments.md)
- [Notifications](notifications.md)
