from decimal import Decimal
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment, PaymentStatus
from app.models.user import UserRole
from tests.conftest import _make_user


async def _create_product(client, seller, auth_headers, *, sku=None, stock=5, price="9.99"):
    r = await client.post(
        "/api/v1/products",
        json={
                "sku": sku or f"SKU-PAY-{uuid4().hex[:6]}",
                "name": "Widget",
                "price": price,
                "stock_quantity": stock,
            },
        headers=auth_headers(seller),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _create_order(client, customer, auth_headers, product_id):
    r = await client.post(
        "/api/v1/orders",
        json={"items": [{"product_id": product_id, "quantity": 1}]},
        headers=auth_headers(customer),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _seed_payment(session: AsyncSession, order_id: str, total: str) -> Payment:
    payment = Payment(
        order_id=order_id,
        amount=Decimal(total),
        status=PaymentStatus.INITIATED,
    )
    session.add(payment)
    await session.flush()
    return payment


async def test_get_payment_by_order_happy_path(
    client: AsyncClient, seller, customer, auth_headers, session: AsyncSession
) -> None:
    product = await _create_product(client, seller, auth_headers)
    order = await _create_order(client, customer, auth_headers, product["id"])
    payment = await _seed_payment(session, order["id"], order["total"])

    r = await client.get(f"/api/v1/payments/by-order/{order['id']}", headers=auth_headers(customer))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["id"] == str(payment.id)
    assert data["order_id"] == order["id"]
    assert data["status"] == "initiated"


async def test_get_payment_unauthenticated(client: AsyncClient) -> None:
    r = await client.get(f"/api/v1/payments/by-order/{uuid4()}")
    assert r.status_code == 401


async def test_get_payment_other_customer_forbidden(
    client: AsyncClient, seller, customer, auth_headers, session: AsyncSession
) -> None:
    other = await _make_user(session, role=UserRole.CUSTOMER)

    product = await _create_product(client, seller, auth_headers)
    order = await _create_order(client, customer, auth_headers, product["id"])
    await _seed_payment(session, order["id"], order["total"])

    r = await client.get(f"/api/v1/payments/by-order/{order['id']}", headers=auth_headers(other))
    assert r.status_code == 403


async def test_get_payment_order_not_found(
    client: AsyncClient, customer, auth_headers
) -> None:
    r = await client.get(f"/api/v1/payments/by-order/{uuid4()}", headers=auth_headers(customer))
    assert r.status_code == 404


async def test_get_payment_no_payment_row_yet(
    client: AsyncClient, seller, customer, auth_headers
) -> None:
    product = await _create_product(client, seller, auth_headers)
    order = await _create_order(client, customer, auth_headers, product["id"])

    r = await client.get(f"/api/v1/payments/by-order/{order['id']}", headers=auth_headers(customer))
    assert r.status_code == 404


async def test_get_payment_admin_can_see_any(
    client: AsyncClient, seller, customer, admin, auth_headers, session: AsyncSession
) -> None:
    product = await _create_product(client, seller, auth_headers)
    order = await _create_order(client, customer, auth_headers, product["id"])
    await _seed_payment(session, order["id"], order["total"])

    r = await client.get(f"/api/v1/payments/by-order/{order['id']}", headers=auth_headers(admin))
    assert r.status_code == 200, r.text
