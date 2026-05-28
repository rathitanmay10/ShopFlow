from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import hash_password
from app.models.notification import Notification, NotificationStatus
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product, ProductStatus
from app.models.user import User, UserRole
from app.workers.tasks import process_payment, send_notification
from tests.conftest import _test_settings

_TASKS_SESSION_MAKER = "app.workers.tasks.async_session_maker"


async def test_send_notification_creates_sent_row() -> None:
    settings = _test_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = None
    try:
        async with factory() as s:
            user = User(
                email=f"wn-{uuid4().hex[:8]}@example.com",
                password_hash=hash_password("Password!123"),
                role=UserRole.CUSTOMER,
                is_active=True,
                is_verified=True,
            )
            s.add(user)
            await s.flush()
            await s.commit()
            user_id = user.id

        with patch(_TASKS_SESSION_MAKER, factory):
            await send_notification(
                {}, str(user_id), "email", "order_confirmed", {"order_id": "test-123"}
            )

        async with factory() as s:
            row = (
                await s.execute(select(Notification).where(Notification.user_id == user_id))
            ).scalar_one()
            assert row.status == NotificationStatus.SENT
    finally:
        async with factory() as s:
            if user_id:
                await s.execute(delete(Notification).where(Notification.user_id == user_id))
                await s.execute(delete(User).where(User.id == user_id))
            await s.commit()
        await engine.dispose()


async def test_send_notification_invalid_channel_raises() -> None:
    with pytest.raises(ValueError):
        await send_notification({}, str(uuid4()), "carrier_pigeon", "order_confirmed", {})


async def test_process_payment_terminal_skip_order_not_found() -> None:
    settings = _test_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        with patch(_TASKS_SESSION_MAKER, factory):
            await process_payment({"settings": settings}, str(uuid4()))
    finally:
        await engine.dispose()


async def test_process_payment_terminal_skip_wrong_status() -> None:
    settings = _test_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    customer_id = order_id = None
    try:
        async with factory() as s:
            customer = User(
                email=f"wp-c-{uuid4().hex[:8]}@example.com",
                password_hash=hash_password("Password!123"),
                role=UserRole.CUSTOMER,
                is_active=True,
                is_verified=True,
            )
            s.add(customer)
            await s.flush()
            order = Order(
                customer_id=customer.id,
                status=OrderStatus.PENDING,
                total=Decimal("9.99"),
            )
            s.add(order)
            await s.flush()
            await s.commit()
            customer_id = customer.id
            order_id = order.id

        with patch(_TASKS_SESSION_MAKER, factory):
            await process_payment({"settings": settings}, str(order_id))
    finally:
        async with factory() as s:
            if order_id:
                await s.execute(delete(Order).where(Order.id == order_id))
            if customer_id:
                await s.execute(delete(User).where(User.id == customer_id))
            await s.commit()
        await engine.dispose()


async def test_process_payment_success_path() -> None:
    settings = _test_settings().model_copy(update={"payment_success_rate": 1.0})
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    seller_id = customer_id = product_id = order_id = None
    try:
        async with factory() as s:
            seller = User(
                email=f"ws-s-{uuid4().hex[:8]}@example.com",
                password_hash=hash_password("Password!123"),
                role=UserRole.SELLER,
                is_active=True,
                is_verified=True,
            )
            customer = User(
                email=f"ws-c-{uuid4().hex[:8]}@example.com",
                password_hash=hash_password("Password!123"),
                role=UserRole.CUSTOMER,
                is_active=True,
                is_verified=True,
            )
            s.add_all([seller, customer])
            await s.flush()
            product = Product(
                sku=f"SKU-WS-{uuid4().hex[:6]}",
                name="Test Product",
                price=Decimal("9.99"),
                seller_id=seller.id,
                stock_quantity=5,
                status=ProductStatus.ACTIVE,
            )
            s.add(product)
            await s.flush()
            order = Order(
                customer_id=customer.id,
                status=OrderStatus.PAYMENT_PROCESSING,
                total=Decimal("9.99"),
            )
            s.add(order)
            await s.flush()
            s.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=1,
                    unit_price=Decimal("9.99"),
                )
            )
            await s.flush()
            await s.commit()
            seller_id = seller.id
            customer_id = customer.id
            product_id = product.id
            order_id = order.id

        with patch(_TASKS_SESSION_MAKER, factory):
            await process_payment({"settings": settings}, str(order_id))

        async with factory() as s:
            refreshed = await s.get(Order, order_id)
            assert refreshed is not None
            assert refreshed.status == OrderStatus.CONFIRMED
    finally:
        async with factory() as s:
            if order_id:
                # CASCADE: order → order_items, order → payments → payment_events
                await s.execute(delete(Order).where(Order.id == order_id))
            if product_id:
                await s.execute(delete(Product).where(Product.id == product_id))
            if seller_id:
                await s.execute(delete(User).where(User.id == seller_id))
            if customer_id:
                await s.execute(delete(User).where(User.id == customer_id))
            await s.commit()
        await engine.dispose()
