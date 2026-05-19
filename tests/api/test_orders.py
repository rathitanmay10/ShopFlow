from httpx import AsyncClient


async def _create_product(client, seller, auth_headers, *, sku="SKU-O", stock=5, price="10.00"):
    r = await client.post(
        "/api/v1/products",
        json={"sku": sku, "name": "X", "price": price, "stock_quantity": stock},
        headers=auth_headers(seller),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_order_happy_path(client: AsyncClient, seller, customer, auth_headers) -> None:
    product = await _create_product(client, seller, auth_headers, stock=5, price="3.50")

    r = await client.post(
        "/api/v1/orders",
        json={"items": [{"product_id": product["id"], "quantity": 2}]},
        headers=auth_headers(customer),
    )
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["status"] == "payment_processing"
    assert order["total"] == "7.00"
    assert len(order["items"]) == 1
    assert order["items"][0]["quantity"] == 2

    # Stock should reflect decrement
    r = await client.get(f"/api/v1/products/{product['id']}")
    assert r.json()["stock_quantity"] == 3


async def test_oversell_rejected(client: AsyncClient, seller, customer, auth_headers) -> None:
    product = await _create_product(client, seller, auth_headers, stock=1)
    r = await client.post(
        "/api/v1/orders",
        json={"items": [{"product_id": product["id"], "quantity": 2}]},
        headers=auth_headers(customer),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invariant_violation"


async def test_cancel_restores_stock(client: AsyncClient, seller, customer, auth_headers) -> None:
    product = await _create_product(client, seller, auth_headers, stock=3)
    create = await client.post(
        "/api/v1/orders",
        json={"items": [{"product_id": product["id"], "quantity": 2}]},
        headers=auth_headers(customer),
    )
    order_id = create.json()["id"]

    r = await client.post(f"/api/v1/orders/{order_id}/cancel", headers=auth_headers(customer))
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"

    r = await client.get(f"/api/v1/products/{product['id']}")
    assert r.json()["stock_quantity"] == 3


async def test_other_customer_cannot_view_order(
    client: AsyncClient, seller, customer, auth_headers, session
) -> None:
    from app.models.user import UserRole
    from tests.conftest import _make_user

    other = await _make_user(session, role=UserRole.CUSTOMER)

    product = await _create_product(client, seller, auth_headers, stock=2)
    create = await client.post(
        "/api/v1/orders",
        json={"items": [{"product_id": product["id"], "quantity": 1}]},
        headers=auth_headers(customer),
    )
    oid = create.json()["id"]

    r = await client.get(f"/api/v1/orders/{oid}", headers=auth_headers(other))
    assert r.status_code == 403
