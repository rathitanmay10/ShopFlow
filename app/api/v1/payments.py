from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUserDep, SessionDep, SettingsDep
from app.schemas.payment import PaymentRead
from app.services.payment import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])


def _payment_service(session: SessionDep, settings: SettingsDep) -> PaymentService:
    return PaymentService(session, settings)


PaymentServiceDep = Annotated[PaymentService, Depends(_payment_service)]


@router.get("/by-order/{order_id}")
async def get_payment_by_order(
    order_id: UUID,
    user: CurrentUserDep,
    service: PaymentServiceDep,
) -> PaymentRead:
    return await service.get_for_order(order_id, user)
