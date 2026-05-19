from httpx import AsyncClient


async def test_seller_can_create_and_list_product(
    client: AsyncClient, seller, auth_headers
) -> None:
    payload = {
        "sku": "SKU-1",
        "name": "Plumbus",
        "description": "All-purpose home device",
        "price": "12.50",
        "stock_quantity": 3,
    }
    r = await client.post("/api/v1/products", json=payload, headers=auth_headers(seller))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["sku"] == "SKU-1"
    assert body["seller_id"] == str(seller.id)
    assert body["stock_quantity"] == 3
    assert body["status"] == "active"

    r = await client.get("/api/v1/products")
    assert r.status_code == 200
    page = r.json()
    assert page["total"] == 1
    assert page["items"][0]["sku"] == "SKU-1"


async def test_customer_cannot_create_product(client: AsyncClient, customer, auth_headers) -> None:
    payload = {"sku": "SKU-2", "name": "Thing", "price": "9.99", "stock_quantity": 1}
    r = await client.post("/api/v1/products", json=payload, headers=auth_headers(customer))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "permission_denied"


async def test_duplicate_sku_rejected(client: AsyncClient, seller, auth_headers) -> None:
    payload = {"sku": "DUP", "name": "X", "price": "1.00", "stock_quantity": 1}
    r = await client.post("/api/v1/products", json=payload, headers=auth_headers(seller))
    assert r.status_code == 201
    r = await client.post("/api/v1/products", json=payload, headers=auth_headers(seller))
    assert r.status_code == 409


async def test_other_seller_cannot_update(
    client: AsyncClient, seller, auth_headers, session
) -> None:
    from app.models.user import UserRole
    from tests.conftest import _make_user

    other = await _make_user(session, role=UserRole.SELLER)

    create = await client.post(
        "/api/v1/products",
        json={"sku": "OWN-1", "name": "Own", "price": "5.00", "stock_quantity": 1},
        headers=auth_headers(seller),
    )
    pid = create.json()["id"]
    r = await client.put(
        f"/api/v1/products/{pid}",
        json={"name": "Stolen"},
        headers=auth_headers(other),
    )
    assert r.status_code == 403


async def test_soft_delete_excludes_from_list(client: AsyncClient, seller, auth_headers) -> None:
    r = await client.post(
        "/api/v1/products",
        json={"sku": "DEL-1", "name": "Del", "price": "1.00", "stock_quantity": 1},
        headers=auth_headers(seller),
    )
    pid = r.json()["id"]
    r = await client.delete(f"/api/v1/products/{pid}", headers=auth_headers(seller))
    assert r.status_code == 204
    r = await client.get("/api/v1/products")
    assert r.json()["total"] == 0
    r = await client.get(f"/api/v1/products/{pid}")
    assert r.status_code == 404
