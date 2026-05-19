import asyncio
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


async def _drop_schema(database_url: str) -> None:
    eng = create_async_engine(database_url)
    try:
        async with eng.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
    finally:
        await eng.dispose()


def _alembic_upgrade(database_url: str) -> None:
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


def pytest_configure(config: pytest.Config) -> None:
    """Wipe + migrate the test DB once before any tests run.

    Done synchronously here (outside any asyncio event loop) so per-test fixtures
    can each spin up their own engine/loop without sharing async state.
    """
    settings = _test_settings()
    asyncio.run(_drop_schema(settings.database_url))
    _alembic_upgrade(settings.database_url)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Per-test AsyncSession with savepoint-based rollback.

    Each test creates its own engine + connection so we never share async state
    across the event loops pytest-asyncio gives to each test function.

    Pattern: open a real transaction on the connection, attach an AsyncSession
    that operates inside a SAVEPOINT. Application-side `session.commit()` releases
    the savepoint; the outer transaction is rolled back at teardown.
    """
    settings = _test_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    connection = await engine.connect()
    trans = await connection.begin()
    sess = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield sess
    finally:
        await sess.close()
        if trans.is_active:
            await trans.rollback()
        await connection.close()
        await engine.dispose()


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
        email=email or f"u-{uuid4().hex[:8]}@example.com",
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
