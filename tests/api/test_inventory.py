from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserRole
from tests.conftest import _make_user


async def _create_product(
    client: AsyncClient, seller, auth_headers, *, sku: str = "SKU-INV", stock: int = 10
) -> dict:
    r = await client.post(
        "/api/v1/products",
        json={"sku": sku, "name": "Widget", "price": "5.00", "stock_quantity": stock},
        headers=auth_headers(seller),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_seller_can_adjust_own_product(client: AsyncClient, seller, auth_headers) -> None:
    product = await _create_product(client, seller, auth_headers, stock=10)
    pid = product["id"]

    r = await client.post(
        f"/api/v1/products/{pid}/inventory/adjust",
        json={"delta": 5},
        headers=auth_headers(seller),
    )
    assert r.status_code == 200, r.text
    assert r.json()["stock_quantity"] == 15


async def test_seller_can_decrease_own_product(client: AsyncClient, seller, auth_headers) -> None:
    product = await _create_product(client, seller, auth_headers, sku="SKU-DEC", stock=10)
    pid = product["id"]

    r = await client.post(
        f"/api/v1/products/{pid}/inventory/adjust",
        json={"delta": -3},
        headers=auth_headers(seller),
    )
    assert r.status_code == 200
    assert r.json()["stock_quantity"] == 7


async def test_seller_cannot_adjust_other_sellers_product(
    client: AsyncClient, seller, auth_headers, session: AsyncSession
) -> None:
    other = await _make_user(session, role=UserRole.SELLER)
    product = await _create_product(client, seller, auth_headers, sku="SKU-OTH", stock=10)
    pid = product["id"]

    r = await client.post(
        f"/api/v1/products/{pid}/inventory/adjust",
        json={"delta": 1},
        headers=auth_headers(other),
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "permission_denied"


async def test_admin_can_adjust_any_product(
    client: AsyncClient, seller, admin, auth_headers
) -> None:
    product = await _create_product(client, seller, auth_headers, sku="SKU-ADM", stock=10)
    pid = product["id"]

    r = await client.post(
        f"/api/v1/products/{pid}/inventory/adjust",
        json={"delta": 20, "note": "restock"},
        headers=auth_headers(admin),
    )
    assert r.status_code == 200
    assert r.json()["stock_quantity"] == 30


async def test_adjust_unknown_product_returns_404(
    client: AsyncClient, seller, auth_headers
) -> None:
    import uuid

    r = await client.post(
        f"/api/v1/products/{uuid.uuid4()}/inventory/adjust",
        json={"delta": 1},
        headers=auth_headers(seller),
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


async def test_zero_delta_rejected(client: AsyncClient, seller, auth_headers) -> None:
    product = await _create_product(client, seller, auth_headers, sku="SKU-ZERO", stock=5)
    r = await client.post(
        f"/api/v1/products/{product['id']}/inventory/adjust",
        json={"delta": 0},
        headers=auth_headers(seller),
    )
    assert r.status_code == 422
