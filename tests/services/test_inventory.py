import asyncio
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.core.exceptions import InvariantViolationError
from app.models.inventory import InventoryMovement, MovementReason
from app.models.product import Product, ProductStatus
from app.services.inventory import InventoryService


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


@pytest.mark.asyncio
async def test_decrement_succeeds_when_stock_available(session, seller) -> None:
    product = await _make_product(session, seller, stock=5)
    svc = InventoryService(session, get_settings())
    new_qty = await svc.decrement(product.id, 3, reason=MovementReason.ORDER, actor_id=seller.id)
    assert new_qty == 2

    moves = (
        await session.execute(
            InventoryMovement.__table__.select().where(InventoryMovement.product_id == product.id)
        )
    ).all()
    assert len(moves) == 1


@pytest.mark.asyncio
async def test_decrement_raises_on_insufficient_stock(session, seller) -> None:
    product = await _make_product(session, seller, stock=1, sku="SKU-INV-2")
    svc = InventoryService(session, get_settings())
    with pytest.raises(InvariantViolationError) as exc:
        await svc.decrement(product.id, 2, reason=MovementReason.ORDER)
    assert "insufficient_stock" in str(exc.value)


@pytest.mark.asyncio
async def test_restore_brings_stock_back(session, seller) -> None:
    product = await _make_product(session, seller, stock=3, sku="SKU-INV-3")
    svc = InventoryService(session, get_settings())
    await svc.decrement(product.id, 3, reason=MovementReason.ORDER)
    await session.refresh(product)
    assert product.stock_quantity == 0
    assert product.status == ProductStatus.OUT_OF_STOCK

    await svc.restore(product.id, 3, reason=MovementReason.CANCEL)
    await session.refresh(product)
    assert product.stock_quantity == 3
    assert product.status == ProductStatus.ACTIVE


@pytest.mark.asyncio
async def test_concurrent_decrement_on_last_unit(engine, seller) -> None:
    """Two parallel sessions race for the last unit. Exactly one succeeds."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = get_settings()
    async with factory() as setup:
        product = await _make_product(setup, seller, stock=1, sku="SKU-RACE")
        await setup.commit()
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

    # Cleanup
    async with factory() as s:
        prod = await s.get(Product, product_id)
        if prod is not None:
            await s.delete(prod)
            await s.commit()
