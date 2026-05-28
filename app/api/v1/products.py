from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUserDep, SessionDep
from app.models.product import ProductStatus
from app.repositories.product import ProductRepository
from app.schemas.product import (
    ProductCreate,
    ProductPage,
    ProductRead,
    ProductSort,
    ProductUpdate,
)
from app.services.product import ProductService

router = APIRouter(prefix="/products", tags=["products"])


def _product_service(session: SessionDep) -> ProductService:
    return ProductService(ProductRepository(session))


ProductServiceDep = Annotated[ProductService, Depends(_product_service)]


@router.get("")
async def list_products(
    service: ProductServiceDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    category_id: Annotated[UUID | None, Query()] = None,
    min_price: Annotated[Decimal | None, Query(ge=0)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0)] = None,
    status_filter: Annotated[ProductStatus | None, Query(alias="status")] = None,
    sort: Annotated[ProductSort, Query()] = ProductSort.NEWEST,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProductPage:
    items, total = await service.list_(
        q=q,
        category_id=category_id,
        min_price=min_price,
        max_price=max_price,
        status=status_filter,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return ProductPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/{product_id}")
async def get_product(product_id: UUID, service: ProductServiceDep) -> ProductRead:
    return await service.get(product_id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    user: CurrentUserDep,
    session: SessionDep,
    service: ProductServiceDep,
) -> ProductRead:
    product = await service.create(payload, user)
    await session.commit()
    return product


@router.put("/{product_id}")
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    user: CurrentUserDep,
    session: SessionDep,
    service: ProductServiceDep,
) -> ProductRead:
    product = await service.update(product_id, payload, user)
    await session.commit()
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: UUID,
    user: CurrentUserDep,
    session: SessionDep,
    service: ProductServiceDep,
) -> None:
    await service.soft_delete(product_id, user)
    await session.commit()
