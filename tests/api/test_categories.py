from httpx import AsyncClient


async def test_list_categories_empty(client: AsyncClient) -> None:
    r = await client.get("/api/v1/categories")
    assert r.status_code == 200
    assert r.json() == []


async def test_admin_can_create_category(client: AsyncClient, admin, auth_headers) -> None:
    r = await client.post(
        "/api/v1/categories",
        json={"name": "Electronics", "slug": "electronics"},
        headers=auth_headers(admin),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Electronics"
    assert body["slug"] == "electronics"
    assert "id" in body
    assert "created_at" in body


async def test_list_returns_created_categories(client: AsyncClient, admin, auth_headers) -> None:
    for name, slug in [("Books", "books"), ("Apparel", "apparel")]:
        await client.post(
            "/api/v1/categories",
            json={"name": name, "slug": slug},
            headers=auth_headers(admin),
        )

    r = await client.get("/api/v1/categories")
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert names == ["Apparel", "Books"]  # ordered by name


async def test_customer_cannot_create_category(
    client: AsyncClient, customer, auth_headers
) -> None:
    r = await client.post(
        "/api/v1/categories",
        json={"name": "Forbidden", "slug": "forbidden"},
        headers=auth_headers(customer),
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "permission_denied"


async def test_seller_cannot_create_category(client: AsyncClient, seller, auth_headers) -> None:
    r = await client.post(
        "/api/v1/categories",
        json={"name": "Forbidden", "slug": "forbidden"},
        headers=auth_headers(seller),
    )
    assert r.status_code == 403


async def test_duplicate_slug_rejected(client: AsyncClient, admin, auth_headers) -> None:
    payload = {"name": "Gadgets", "slug": "gadgets"}
    r = await client.post("/api/v1/categories", json=payload, headers=auth_headers(admin))
    assert r.status_code == 201
    r = await client.post(
        "/api/v1/categories",
        json={"name": "Gadgets 2", "slug": "gadgets"},
        headers=auth_headers(admin),
    )
    assert r.status_code == 409
