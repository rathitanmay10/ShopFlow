from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import SessionDep, require_role
from app.models.user import UserRole
from app.schemas.category import CategoryCreate, CategoryRead
from app.services.category import CategoryService

router = APIRouter(prefix="/categories", tags=["categories"])


def _category_service(session: SessionDep) -> CategoryService:
    return CategoryService(session)


CategoryServiceDep = Annotated[CategoryService, Depends(_category_service)]


@router.get("")
async def list_categories(service: CategoryServiceDep) -> list[CategoryRead]:
    cats = await service.list_()
    return [CategoryRead.model_validate(c) for c in cats]


@router.post(
    "",
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    payload: CategoryCreate, service: CategoryServiceDep, session: SessionDep
) -> CategoryRead:
    cat = await service.create(payload)
    await session.commit()
    return CategoryRead.model_validate(cat)
