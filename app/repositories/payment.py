from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.payment import Payment


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_order_id(self, order_id: UUID) -> Payment | None:
        return await self.session.scalar(
            select(Payment)
            .options(selectinload(Payment.events))
            .where(Payment.order_id == order_id)
        )
