from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, SessionDep, SettingsDep
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models.inventory import MovementReason
from app.models.user import UserRole
from app.repositories.product import ProductRepository
from app.services.inventory import InventoryService

router = APIRouter(prefix="/products/{product_id}/inventory", tags=["inventory"])


class InventoryAdjustIn(BaseModel):
    delta: int = Field(description="positive to add stock, negative to remove; nonzero")
    note: str | None = Field(default=None, max_length=255)


class InventoryAdjustOut(BaseModel):
    stock_quantity: int


@router.post("/adjust", status_code=status.HTTP_200_OK)
async def adjust_inventory(
    product_id: UUID,
    payload: InventoryAdjustIn,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> InventoryAdjustOut:
    product = await ProductRepository(session).get(product_id)
    if product is None:
        raise NotFoundError("product_not_found")
    is_admin = user.role == UserRole.ADMIN
    if not is_admin and product.seller_id != user.id:
        raise PermissionDeniedError("not_product_owner")
    reason = MovementReason.ADMIN_ADJUST if is_admin else MovementReason.SELLER_ADJUST
    service = InventoryService(session, settings)
    new_qty = await service.adjust(
        product_id, payload.delta, reason=reason, actor_id=user.id, note=payload.note
    )
    await session.commit()
    return InventoryAdjustOut(stock_quantity=new_qty)
