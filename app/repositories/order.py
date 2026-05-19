from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import Order


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, order_id: UUID) -> Order | None:
        return await self.session.scalar(
            select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
        )

    async def list_(
        self,
        *,
        customer_id: UUID | None = None,
        page: int,
        page_size: int,
    ) -> tuple[list[Order], int]:
        base = select(Order)
        if customer_id is not None:
            base = base.where(Order.customer_id == customer_id)
        total = (
            await self.session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            (
                await self.session.execute(
                    base.options(selectinload(Order.items))
                    .order_by(Order.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total
