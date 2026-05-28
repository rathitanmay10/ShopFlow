from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.category import Category


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_slug(self, slug: str) -> Category | None:
        result = await self.session.execute(select(Category).where(Category.slug == slug))
        return result.scalar_one_or_none()

    async def list_(self) -> list[Category]:
        rows = (
            (await self.session.execute(select(Category).order_by(Category.name))).scalars().all()
        )
        return list(rows)

    async def create(self, category: Category) -> Category:
        self.session.add(category)
        try:
            await self.session.flush()
        except IntegrityError:
            raise ConflictError("slug_taken")
        await self.session.refresh(category)
        return category
