from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MovementReason(StrEnum):
    ORDER = "order"
    CANCEL = "cancel"
    ADMIN_ADJUST = "admin_adjust"
    RESTOCK = "restock"
    SELLER_ADJUST = "seller_adjust"


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[MovementReason] = mapped_column(
        Enum(MovementReason, name="movement_reason"), nullable=False
    )
    order_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    actor_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
