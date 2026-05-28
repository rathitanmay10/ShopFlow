from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationChannel
from app.models.user import UserRole
from app.services.notification import NotificationService
from tests.conftest import _make_user


async def _seed(session: AsyncSession, user_id, event_type="order_confirmed"):
    return await NotificationService(session).send(
        user_id, NotificationChannel.EMAIL, event_type, {"x": "y"}
    )


async def test_list_notifications_returns_own(
    client: AsyncClient, customer, auth_headers, session: AsyncSession
) -> None:
    notif = await _seed(session, customer.id)

    r = await client.get("/api/v1/notifications", headers=auth_headers(customer))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == str(notif.id)


async def test_list_notifications_empty(client: AsyncClient, customer, auth_headers) -> None:
    r = await client.get("/api/v1/notifications", headers=auth_headers(customer))
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []


async def test_list_notifications_pagination(
    client: AsyncClient, customer, auth_headers, session: AsyncSession
) -> None:
    for i in range(3):
        await _seed(session, customer.id, event_type=f"event_{i}")

    r = await client.get("/api/v1/notifications?page=1&page_size=2", headers=auth_headers(customer))
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2

    r2 = await client.get(
        "/api/v1/notifications?page=2&page_size=2", headers=auth_headers(customer)
    )
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["total"] == 3
    assert len(data2["items"]) == 1


async def test_list_notifications_other_user_not_visible(
    client: AsyncClient, customer, auth_headers, session: AsyncSession
) -> None:
    other = await _make_user(session, role=UserRole.CUSTOMER)
    await _seed(session, customer.id)
    await _seed(session, other.id)

    r = await client.get("/api/v1/notifications", headers=auth_headers(customer))
    assert r.status_code == 200
    assert r.json()["total"] == 1


async def test_list_notifications_unauthenticated(client: AsyncClient) -> None:
    r = await client.get("/api/v1/notifications")
    assert r.status_code == 401
