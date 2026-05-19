from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, order_id: UUID) -> Order | None:
        return await self.session.get(Order, order_id)

    async def list_for_customer(
        self, customer_id: UUID, *, page: int, page_size: int
    ) -> tuple[list[Order], int]:
        stmt = (
            select(Order)
            .where(Order.customer_id == customer_id)
            .order_by(Order.created_at.desc())
        )
        total = (
            await self.session.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        rows = (
            await self.session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
        ).scalars().all()
        return list(rows), total

    async def list_all(self, *, page: int, page_size: int) -> tuple[list[Order], int]:
        stmt = select(Order).order_by(Order.created_at.desc())
        total = (
            await self.session.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        rows = (
            await self.session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
        ).scalars().all()
        return list(rows), total
