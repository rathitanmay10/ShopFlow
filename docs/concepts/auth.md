# Auth

## Tokens

JWT bearer, HS256. Two types:

| Token | Default TTL | Env var | Purpose |
|---|---|---|---|
| Access | 15 min | `JWT_ACCESS_TTL_MINUTES` | Sent on every request as `Authorization: Bearer ...` |
| Refresh | 14 d | `JWT_REFRESH_TTL_DAYS` | Exchanged for a new pair via `POST /auth/refresh` |

Both are signed with `JWT_SECRET`. Rotate the secret by setting a new value and forcing all clients to re-login.

`subject_uuid(payload)` in `app/core/security.py` extracts the user UUID from a decoded payload. **Never** do `UUID(payload["sub"])` + try/except in a router — use the helper.

## Password hashing

Direct `bcrypt` library. Hash on register; verify on login. Cost factor is the library default.

## Roles (RBAC)

| Role | Granted on register? | Capabilities |
|---|---|---|
| `customer` | yes (default) | Place orders, view own orders / payments / notifications |
| `seller` | no — manual / admin promotion | Create + manage own products; adjust own inventory |
| `admin` | no — manual | Everything: cross-user reads, suspend users, view audit logs |

Enforced via `require_role(...)` dependency on routers or individual endpoints.

## Ownership checks

RBAC is necessary but not sufficient. A seller can manage their **own** products only, and a customer can read their **own** orders / payments / notifications only. These checks happen in the **service** layer:

```python
if actor.role != UserRole.ADMIN and order.customer_id != actor.id:
    raise PermissionDeniedError("not_order_owner")
```

Admins bypass ownership checks.

## Throttling

| Surface | Limit | Implementation |
|---|---|---|
| Failed login | `RATE_LIMIT_AUTH_PER_MIN` (default 5/min) per IP+email | Redis fixed window |
| Everything else | `RATE_LIMIT_DEFAULT_PER_MIN` (default 120/min) per IP | Redis fixed window |

Both fall **open** if Redis is unreachable (warning logged). This is a deliberate availability trade-off: when Redis is down, we'd rather serve traffic than block it.

## Suspension

`PATCH /admin/users/{id}/suspend` flips `is_active = false`. `get_current_user` rejects suspended users with `401`. Existing access tokens still decode validly but are rejected at the dependency layer.

## What is NOT done

- No password reset flow.
- No token revocation list — once a token is issued, it's valid until expiry. Rotate `JWT_SECRET` to nuke all sessions.
- No 2FA / WebAuthn.
- No "logout" endpoint — clients drop tokens locally.
