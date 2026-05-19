from httpx import AsyncClient


async def test_register_and_login(client: AsyncClient) -> None:
    payload = {
        "email": "alice@example.com",
        "password": "Password!123",
        "role": "customer",
    }
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == payload["email"]
    assert body["role"] == "customer"

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert r.status_code == 200, r.text
    tokens = r.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["token_type"] == "bearer"


async def test_register_duplicate_email(client: AsyncClient) -> None:
    payload = {"email": "dup@example.com", "password": "Password!123"}
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 201
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


async def test_login_wrong_password(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "x@example.com", "password": "Password!123"},
    )
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "x@example.com", "password": "wrong-pass-9999"},
    )
    assert r.status_code == 401


async def test_refresh_rotates(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "r@example.com", "password": "Password!123"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "r@example.com", "password": "Password!123"},
    )
    refresh = login.json()["refresh_token"]
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    assert r.json()["access_token"]


async def test_refresh_with_access_token_rejected(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "rj@example.com", "password": "Password!123"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "rj@example.com", "password": "Password!123"},
    )
    access = login.json()["access_token"]
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": access})
    assert r.status_code == 401
