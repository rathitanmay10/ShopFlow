from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from tests.conftest import _make_user
from app.models.user import UserRole


async def test_admin_can_suspend_user(
    client: AsyncClient, admin, auth_headers, session: AsyncSession
) -> None:
    target = await _make_user(session, role=UserRole.CUSTOMER)
    assert target.is_active is True

    r = await client.patch(
        f"/api/v1/admin/users/{target.id}/suspend",
        json={"suspend": True},
        headers=auth_headers(admin),
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"is_active": False}

    await session.refresh(target)
    assert target.is_active is False


async def test_admin_can_unsuspend_user(
    client: AsyncClient, admin, auth_headers, session: AsyncSession
) -> None:
    target = await _make_user(session, role=UserRole.CUSTOMER)

    await client.patch(
        f"/api/v1/admin/users/{target.id}/suspend",
        json={"suspend": True},
        headers=auth_headers(admin),
    )
    r = await client.patch(
        f"/api/v1/admin/users/{target.id}/suspend",
        json={"suspend": False},
        headers=auth_headers(admin),
    )
    assert r.status_code == 200
    assert r.json() == {"is_active": True}

    await session.refresh(target)
    assert target.is_active is True


async def test_suspend_nonexistent_user_returns_404(
    client: AsyncClient, admin, auth_headers
) -> None:
    import uuid

    r = await client.patch(
        f"/api/v1/admin/users/{uuid.uuid4()}/suspend",
        json={"suspend": True},
        headers=auth_headers(admin),
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


async def test_suspend_writes_audit_log(
    client: AsyncClient, admin, auth_headers, session: AsyncSession
) -> None:
    target = await _make_user(session, role=UserRole.CUSTOMER)

    await client.patch(
        f"/api/v1/admin/users/{target.id}/suspend",
        json={"suspend": True},
        headers=auth_headers(admin),
    )

    rows = (
        (
            await session.execute(
                select(AuditLog)
                .where(AuditLog.action == "user_suspended")
                .where(AuditLog.resource_id == str(target.id))
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].actor_id == admin.id
    assert rows[0].resource_type == "user"


async def test_customer_cannot_access_admin_endpoints(
    client: AsyncClient, customer, auth_headers, session: AsyncSession
) -> None:
    target = await _make_user(session, role=UserRole.CUSTOMER)
    r = await client.patch(
        f"/api/v1/admin/users/{target.id}/suspend",
        json={"suspend": True},
        headers=auth_headers(customer),
    )
    assert r.status_code == 403
