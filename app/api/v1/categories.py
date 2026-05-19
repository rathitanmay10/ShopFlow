from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.api.deps import SessionDep, require_role
from app.models.category import Category
from app.models.user import UserRole
from app.schemas.category import CategoryCreate, CategoryRead

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("")
async def list_categories(session: SessionDep) -> list[CategoryRead]:
    rows = (await session.execute(select(Category).order_by(Category.name))).scalars().all()
    return [CategoryRead.model_validate(c) for c in rows]


@router.post(
    "",
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    status_code=status.HTTP_201_CREATED,
)
async def create_category(payload: CategoryCreate, session: SessionDep) -> CategoryRead:
    category = Category(name=payload.name, slug=payload.slug)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return CategoryRead.model_validate(category)
