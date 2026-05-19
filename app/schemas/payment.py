from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.payment import PaymentStatus


class PaymentEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    from_status: PaymentStatus | None
    to_status: PaymentStatus
    reason: str | None
    created_at: datetime


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    amount: Decimal
    currency: str
    status: PaymentStatus
    external_txn_id: str | None
    attempts: int
    events: list[PaymentEventRead]
    created_at: datetime
    updated_at: datetime
