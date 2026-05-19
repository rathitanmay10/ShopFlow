from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings
from app.core.security import TokenType, create_token, hash_password
from app.db import get_async_session
from app.db.base import Base
from app.main import create_app
from app.models.user import User, UserRole


def _test_settings() -> Settings:
    base = get_settings()
    url = base.test_database_url or base.database_url
    return base.model_copy(update={"database_url": url, "jwt_secret": base.jwt_secret or "test-secret"})


@pytest_asyncio.fixture(scope="session")
async def engine():
    settings = _test_settings()
    eng = create_async_engine(settings.database_url, pool_pre_ping=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
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
