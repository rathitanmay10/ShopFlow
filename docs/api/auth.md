# Auth endpoints

JWT bearer (HS256). Access tokens default to 15 min; refresh tokens default to 14 d. Both TTLs configurable via `JWT_ACCESS_TTL_MINUTES` and `JWT_REFRESH_TTL_DAYS`.

## `POST /api/v1/auth/register`

Public. Creates a `customer` user. Email must validate against `email-validator` 2.x (real-looking domains; RFC 6761 special-use TLDs like `.local`, `.test`, `.example` are rejected — `@example.com` does work because it's an allow-listed exception in the validator).

Returns the new user record (no token — caller must `login`).

## `POST /api/v1/auth/login`

Public. Body: `{email, password}`. Returns:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer"
}
```

**Throttling.** Failed-login attempts are counted per IP+email via Redis (`RATE_LIMIT_AUTH_PER_MIN`, default 5/min). Excess attempts return `429 rate_limited`. Falls open if Redis is unreachable.

## `POST /api/v1/auth/refresh`

Public. Body: `{refresh_token}`. Returns a new pair (token rotation). The old refresh token is no longer valid for refresh.

## How protection is enforced

Routers depend on `CurrentUserDep` (decodes the access token, loads the user) and `require_role(...)` (RBAC). UUID extraction from token payloads uses `subject_uuid(payload)` from `app/core/security.py`, not ad-hoc `UUID(payload["sub"])` + try/except.

```python
@router.post("/products", dependencies=[Depends(require_role(UserRole.SELLER, UserRole.ADMIN))])
async def create_product(...): ...
```

Token decode never happens inside a router body.

## Suspended users

Admin can flip `is_active = false` via `PATCH /admin/users/{id}/suspend`. `get_current_user` rejects suspended users with `401`.

## Password hashing

Direct `bcrypt` library (not `passlib`). Hash on register, verify on login.
