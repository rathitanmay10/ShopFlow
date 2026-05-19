import logging
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import InvariantViolationError, NotFoundError
from app.models.inventory import InventoryMovement, MovementReason
from app.models.product import Product, ProductStatus

logger = logging.getLogger(__name__)


class InventoryService:
    """Concurrency-safe stock operations.

    All mutations use atomic `UPDATE ... WHERE stock >= :qty RETURNING ...`
    so two concurrent decrements on the last unit cannot both succeed.
    """

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def decrement(
        self,
        product_id: UUID,
        qty: int,
        *,
        reason: MovementReason,
        order_id: UUID | None = None,
        actor_id: UUID | None = None,
    ) -> int:
        if qty <= 0:
            raise InvariantViolationError("qty_must_be_positive")
        stmt = (
            update(Product)
            .where(
                Product.id == product_id,
                Product.deleted_at.is_(None),
                Product.stock_quantity >= qty,
            )
            .values(stock_quantity=Product.stock_quantity - qty)
            .returning(Product.stock_quantity)
        )
        new_qty = (await self.session.execute(stmt)).scalar_one_or_none()
        if new_qty is None:
            raise InvariantViolationError(
                "insufficient_stock",
                metadata={"product_id": str(product_id), "qty": qty},
            )
        self._record(product_id, -qty, reason, order_id=order_id, actor_id=actor_id)
        await self._maybe_mark_out_of_stock(product_id, new_qty)
        self._maybe_log_low_stock(product_id, new_qty)
        return new_qty

    async def restore(
        self,
        product_id: UUID,
        qty: int,
        *,
        reason: MovementReason = MovementReason.CANCEL,
        order_id: UUID | None = None,
        actor_id: UUID | None = None,
    ) -> int:
        if qty <= 0:
            raise InvariantViolationError("qty_must_be_positive")
        stmt = (
            update(Product)
            .where(Product.id == product_id, Product.deleted_at.is_(None))
            .values(stock_quantity=Product.stock_quantity + qty)
            .returning(Product.stock_quantity)
        )
        new_qty = (await self.session.execute(stmt)).scalar_one_or_none()
        if new_qty is None:
            raise NotFoundError("product_not_found")
        self._record(product_id, qty, reason, order_id=order_id, actor_id=actor_id)
        await self._maybe_mark_active(product_id, new_qty)
        return new_qty

    async def adjust(
        self,
        product_id: UUID,
        delta: int,
        *,
        reason: MovementReason,
        actor_id: UUID | None = None,
        note: str | None = None,
    ) -> int:
        if delta == 0:
            raise InvariantViolationError("delta_must_be_nonzero")
        if delta < 0:
            new_qty = await self.decrement(product_id, -delta, reason=reason, actor_id=actor_id)
        else:
            new_qty = await self.restore(product_id, delta, reason=reason, actor_id=actor_id)
        if note:
            await self._annotate_last_movement(product_id, note)
        return new_qty

    def _record(
        self,
        product_id: UUID,
        delta: int,
        reason: MovementReason,
        *,
        order_id: UUID | None,
        actor_id: UUID | None,
    ) -> None:
        self.session.add(
            InventoryMovement(
                product_id=product_id,
                delta=delta,
                reason=reason,
                order_id=order_id,
                actor_id=actor_id,
            )
        )

    async def _annotate_last_movement(self, product_id: UUID, note: str) -> None:
        await self.session.flush()
        result = await self.session.execute(
            select(InventoryMovement)
            .where(InventoryMovement.product_id == product_id)
            .order_by(InventoryMovement.created_at.desc())
            .limit(1)
        )
        movement = result.scalar_one_or_none()
        if movement is not None:
            movement.note = note

    async def _maybe_mark_out_of_stock(self, product_id: UUID, qty: int) -> None:
        if qty > 0:
            return
        await self.session.execute(
            update(Product)
            .where(Product.id == product_id, Product.status == ProductStatus.ACTIVE)
            .values(status=ProductStatus.OUT_OF_STOCK)
        )

    async def _maybe_mark_active(self, product_id: UUID, qty: int) -> None:
        if qty <= 0:
            return
        await self.session.execute(
            update(Product)
            .where(Product.id == product_id, Product.status == ProductStatus.OUT_OF_STOCK)
            .values(status=ProductStatus.ACTIVE)
        )

    def _maybe_log_low_stock(self, product_id: UUID, qty: int) -> None:
        if qty > self.settings.low_stock_threshold:
            return
        logger.warning(
            "low_stock",
            extra={
                "ctx_product_id": str(product_id),
                "ctx_stock_quantity": qty,
                "ctx_threshold": self.settings.low_stock_threshold,
            },
        )
