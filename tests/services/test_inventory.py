import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import InvariantViolationError
from app.core.security import hash_password
from app.models.inventory import InventoryMovement, MovementReason
from app.models.product import Product, ProductStatus
from app.models.user import User, UserRole
from app.services.inventory import InventoryService
from tests.conftest import _test_settings


async def _make_product(session, seller, *, stock=5, sku="SKU-INV"):
    p = Product(
        sku=sku,
        name="Widget",
        description=None,
        price=Decimal("9.99"),
        category_id=None,
        seller_id=seller.id,
        stock_quantity=stock,
        status=ProductStatus.ACTIVE,
    )
    session.add(p)
    await session.flush()
    await session.refresh(p)
    return p


async def test_decrement_succeeds_when_stock_available(session, seller) -> None:
    product = await _make_product(session, seller, stock=5)
    svc = InventoryService(session, _test_settings())
    new_qty = await svc.decrement(product.id, 3, reason=MovementReason.ORDER, actor_id=seller.id)
    assert new_qty == 2

    moves = (
        await session.execute(
            InventoryMovement.__table__.select().where(InventoryMovement.product_id == product.id)
        )
    ).all()
    assert len(moves) == 1


async def test_decrement_raises_on_insufficient_stock(session, seller) -> None:
    product = await _make_product(session, seller, stock=1, sku="SKU-INV-2")
    svc = InventoryService(session, _test_settings())
    with pytest.raises(InvariantViolationError) as exc:
        await svc.decrement(product.id, 2, reason=MovementReason.ORDER)
    assert "insufficient_stock" in str(exc.value)


async def test_restore_brings_stock_back(session, seller) -> None:
    product = await _make_product(session, seller, stock=3, sku="SKU-INV-3")
    svc = InventoryService(session, _test_settings())
    await svc.decrement(product.id, 3, reason=MovementReason.ORDER)
    await session.refresh(product)
    assert product.stock_quantity == 0
    assert product.status == ProductStatus.OUT_OF_STOCK

    await svc.restore(product.id, 3, reason=MovementReason.CANCEL)
    await session.refresh(product)
    assert product.stock_quantity == 3
    assert product.status == ProductStatus.ACTIVE


async def test_concurrent_decrement_on_last_unit() -> None:
    """Two parallel sessions race for the last unit. Exactly one succeeds.

    Self-contained: needs committed (not savepoint-isolated) rows so both
    parallel sessions see the same product. Cleans up at the end so we don't
    leak rows for the next test run.
    """
    settings = _test_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    seller_id = product_id = None
    try:
        async with factory() as setup:
            seller = User(
                email=f"race-{uuid4().hex[:6]}@example.com",
                password_hash=hash_password("Password!123"),
                role=UserRole.SELLER,
                is_active=True,
                is_verified=True,
            )
            setup.add(seller)
            await setup.flush()
            product = await _make_product(setup, seller, stock=1, sku=f"SKU-RACE-{uuid4().hex[:6]}")
            await setup.commit()
            seller_id = seller.id
            product_id = product.id

        async def attempt() -> bool:
            async with factory() as s:
                try:
                    await InventoryService(s, settings).decrement(
                        product_id, 1, reason=MovementReason.ORDER
                    )
                    await s.commit()
                    return True
                except InvariantViolationError:
                    await s.rollback()
                    return False

        results = await asyncio.gather(attempt(), attempt())
        assert sum(results) == 1, results
    finally:
        async with factory() as s:
            if product_id is not None:
                await s.execute(
                    delete(InventoryMovement).where(InventoryMovement.product_id == product_id)
                )
                await s.execute(delete(Product).where(Product.id == product_id))
            if seller_id is not None:
                await s.execute(delete(User).where(User.id == seller_id))
            await s.commit()
        await engine.dispose()
