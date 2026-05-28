from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product, ProductStatus
from app.schemas.product import ProductSort


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base(self) -> Select[tuple[Product]]:
        return select(Product).where(Product.deleted_at.is_(None))

    async def get(self, product_id: UUID) -> Product | None:
        result = await self.session.execute(self._base().where(Product.id == product_id))
        return result.scalar_one_or_none()

    async def get_many_by_ids(self, ids: list[UUID]) -> list[Product]:
        if not ids:
            return []
        rows = (await self.session.execute(self._base().where(Product.id.in_(ids)))).scalars().all()
        return list(rows)

    async def get_by_sku(self, sku: str) -> Product | None:
        result = await self.session.execute(self._base().where(Product.sku == sku))
        return result.scalar_one_or_none()

    async def list_(
        self,
        *,
        q: str | None,
        category_id: UUID | None,
        min_price: Decimal | None,
        max_price: Decimal | None,
        status: ProductStatus | None,
        sort: ProductSort,
        page: int,
        page_size: int,
    ) -> tuple[list[Product], int]:
        stmt = self._base()
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(func.lower(Product.name).like(like))
        if category_id:
            stmt = stmt.where(Product.category_id == category_id)
        if min_price is not None:
            stmt = stmt.where(Product.price >= min_price)
        if max_price is not None:
            stmt = stmt.where(Product.price <= max_price)
        if status is not None:
            stmt = stmt.where(Product.status == status)

        total = (
            await self.session.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()

        sort_map = {
            ProductSort.NEWEST: Product.created_at.desc(),
            ProductSort.PRICE_ASC: Product.price.asc(),
            ProductSort.PRICE_DESC: Product.price.desc(),
            ProductSort.NAME: Product.name.asc(),
        }
        stmt = stmt.order_by(sort_map[sort]).offset((page - 1) * page_size).limit(page_size)
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total

    async def create(self, product: Product) -> Product:
        self.session.add(product)
        await self.session.flush()
        await self.session.refresh(product)
        return product

    async def soft_delete(self, product: Product) -> None:
        product.deleted_at = datetime.now(UTC)
        await self.session.flush()
