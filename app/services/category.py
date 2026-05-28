from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.category import Category
from app.repositories.category import CategoryRepository
from app.schemas.category import CategoryCreate


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = CategoryRepository(session)

    async def list_(self) -> list[Category]:
        return await self._repo.list_()

    async def create(self, payload: CategoryCreate) -> Category:
        if await self._repo.get_by_slug(payload.slug):
            raise ConflictError("slug_taken")
        return await self._repo.create(Category(name=payload.name, slug=payload.slug))
