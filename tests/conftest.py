import os
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings
from app.core.security import TokenType, create_token, hash_password
from app.db import get_async_session
from app.main import create_app
from app.models.user import User, UserRole

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _test_settings() -> Settings:
    """Settings for the test suite — points at `TEST_DATABASE_URL` from `.env`."""
    base = get_settings()
    url = base.test_database_url or base.database_url
    return base.model_copy(update={"database_url": url})


def _alembic_upgrade(database_url: str) -> None:
    """Run `alembic upgrade head` against the test DB via subprocess.

    Subprocess (not `alembic.command.upgrade` in-process) because our alembic
    env.py uses `asyncio.run`, which can't be called from inside the pytest event
    loop. The subprocess gets a clean event loop of its own.
    """
    env = {**os.environ, "DATABASE_URL": database_url}
    result = subprocess.run(  # noqa: S603
        ["uv", "run", "alembic", "upgrade", "head"],  # noqa: S607
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "alembic upgrade head failed:\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


async def _drop_schema(database_url: str) -> None:
    """Wipe the test DB so each session starts from migration zero."""
    eng = create_async_engine(database_url)
    try:
        async with eng.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
    finally:
        await eng.dispose()


@pytest_asyncio.fixture(scope="session")
async def engine():
    settings = _test_settings()
    await _drop_schema(settings.database_url)
    _alembic_upgrade(settings.database_url)
    eng = create_async_engine(settings.database_url, pool_pre_ping=True)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    connection = await engine.connect()
    trans = await connection.begin()
    factory = async_sessionmaker(bind=connection, expire_on_commit=False)
    async with factory() as sess:
        try:
            yield sess
        finally:
            await trans.rollback()
            await connection.close()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_async_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _make_user(
    session: AsyncSession, *, email: str | None = None, role: UserRole = UserRole.CUSTOMER
) -> User:
    user = User(
        email=email or f"u-{uuid4().hex[:8]}@test.local",
        password_hash=hash_password("Password!123"),
        role=role,
        is_active=True,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def customer(session: AsyncSession) -> User:
    return await _make_user(session, role=UserRole.CUSTOMER)


@pytest_asyncio.fixture
async def seller(session: AsyncSession) -> User:
    return await _make_user(session, role=UserRole.SELLER)


@pytest_asyncio.fixture
async def admin(session: AsyncSession) -> User:
    return await _make_user(session, role=UserRole.ADMIN)


@pytest.fixture
def auth_headers() -> Any:
    def _make(user: User) -> dict[str, str]:
        token = create_token(
            _test_settings(),
            str(user.id),
            TokenType.ACCESS,
            extra={"role": user.role.value},
        )
        return {"Authorization": f"Bearer {token}"}

    return _make
