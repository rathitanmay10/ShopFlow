from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.api.deps import ArqPoolDep, CurrentUserDep, SessionDep, SettingsDep
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
    pool: ArqPoolDep,
) -> InventoryAdjustOut:
    service = InventoryService(session, settings, arq_pool=pool)
    new_qty = await service.adjust_for_actor(
        product_id, payload.delta, actor=user, note=payload.note
    )
    await session.commit()
    return InventoryAdjustOut(stock_quantity=new_qty)
