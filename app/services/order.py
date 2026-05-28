from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    InvariantViolationError,
    NotFoundError,
    PermissionDeniedError,
)
from app.models.inventory import MovementReason
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import ProductStatus
from app.models.user import User, UserRole
from app.repositories.order import OrderRepository
from app.repositories.product import ProductRepository
from app.schemas.order import OrderCreate
from app.services.inventory import InventoryService
from app.services.order_state import CANCELLABLE, assert_transition


class OrderService:
    def __init__(
        self,
        session: AsyncSession,
        orders: OrderRepository,
        inventory: InventoryService,
        settings: Settings,
    ) -> None:
        self.session = session
        self.orders = orders
        self.inventory = inventory
        self.settings = settings

    async def create_order(self, customer: User, payload: OrderCreate) -> Order:
        product_ids = [it.product_id for it in payload.items]
        rows = await ProductRepository(self.session).get_many_by_ids(product_ids)
        product_map = {p.id: p for p in rows}
        missing = set(product_ids) - set(product_map.keys())
        if missing:
            raise NotFoundError(
                "product_not_found", metadata={"missing": [str(m) for m in missing]}
            )

        total = Decimal("0")
        order_items: list[OrderItem] = []
        for line in payload.items:
            product = product_map[line.product_id]
            if product.status == ProductStatus.DISCONTINUED:
                raise InvariantViolationError(
                    "product_discontinued", metadata={"product_id": str(product.id)}
                )
            order_items.append(
                OrderItem(
                    product_id=product.id,
                    quantity=line.quantity,
                    unit_price=product.price,
                )
            )
            total += product.price * line.quantity

        order = Order(
            customer_id=customer.id,
            status=OrderStatus.PENDING,
            total=total,
            items=order_items,
        )
        self.session.add(order)
        await self.session.flush()

        for line in payload.items:
            await self.inventory.decrement(
                line.product_id,
                line.quantity,
                reason=MovementReason.ORDER,
                order_id=order.id,
                actor_id=customer.id,
            )

        assert_transition(order.status, OrderStatus.PAYMENT_PROCESSING)
        order.status = OrderStatus.PAYMENT_PROCESSING
        # Re-fetch via repository so `items` is loaded with selectinload — the
        # in-memory collection set at construction is not reliably serializable
        # after flush in async mode.
        reloaded = await self.orders.get(order.id)
        assert reloaded is not None  # we just inserted it
        return reloaded

    async def get(self, order_id: UUID, actor: User) -> Order:
        order = await self.orders.get(order_id)
        if order is None:
            raise NotFoundError("order_not_found")
        if actor.role != UserRole.ADMIN and order.customer_id != actor.id:
            raise PermissionDeniedError("not_order_owner")
        return order

    async def list_for_actor(
        self, actor: User, *, page: int, page_size: int
    ) -> tuple[list[Order], int]:
        customer_id = None if actor.role == UserRole.ADMIN else actor.id
        return await self.orders.list_(customer_id=customer_id, page=page, page_size=page_size)

    async def cancel(self, order_id: UUID, actor: User) -> Order:
        order = await self.get(order_id, actor)
        if order.status not in CANCELLABLE:
            raise InvariantViolationError(
                "order_not_cancellable", metadata={"status": order.status.value}
            )
        assert_transition(order.status, OrderStatus.CANCELLED)
        order.status = OrderStatus.CANCELLED
        for item in order.items:
            await self.inventory.restore(
                item.product_id,
                item.quantity,
                reason=MovementReason.CANCEL,
                order_id=order.id,
                actor_id=actor.id,
            )
        # Re-fetch so `items` collection is freshly bound after mutations.
        reloaded = await self.orders.get(order.id)
        assert reloaded is not None
        return reloaded
