from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUserDep, SessionDep, SettingsDep
from app.repositories.order import OrderRepository
from app.schemas.order import OrderCreate, OrderPage, OrderRead
from app.services.inventory import InventoryService
from app.services.order import OrderService
from app.workers.queue import enqueue

router = APIRouter(prefix="/orders", tags=["orders"])


def _order_service(session: SessionDep, settings: SettingsDep) -> OrderService:
    return OrderService(
        session,
        OrderRepository(session),
        InventoryService(session, settings),
        settings,
    )


OrderServiceDep = Annotated[OrderService, Depends(_order_service)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
    service: OrderServiceDep,
) -> OrderRead:
    order = await service.create_order(user, payload)
    await session.commit()
    await enqueue(settings, "process_payment", str(order.id))
    return OrderRead.model_validate(order)


@router.get("")
async def list_orders(
    user: CurrentUserDep,
    service: OrderServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> OrderPage:
    items, total = await service.list_for_actor(user, page=page, page_size=page_size)
    return OrderPage(
        items=[OrderRead.model_validate(o) for o in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{order_id}")
async def get_order(
    order_id: UUID,
    user: CurrentUserDep,
    service: OrderServiceDep,
) -> OrderRead:
    order = await service.get(order_id, user)
    return OrderRead.model_validate(order)


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: UUID,
    user: CurrentUserDep,
    session: SessionDep,
    service: OrderServiceDep,
) -> OrderRead:
    order = await service.cancel(order_id, user)
    await session.commit()
    return OrderRead.model_validate(order)
