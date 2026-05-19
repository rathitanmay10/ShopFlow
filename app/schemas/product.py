from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.product import ProductStatus


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    price: Decimal = Field(gt=0, decimal_places=2, max_digits=12)
    category_id: UUID | None = None
    stock_quantity: int = Field(default=0, ge=0)


class ProductUpdate(BaseModel):
    """Mutable product attributes.

    Stock changes go through `POST /products/{id}/inventory/adjust`, not here —
    so every movement is recorded in `inventory_movements`.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0, decimal_places=2, max_digits=12)
    category_id: UUID | None = None
    status: ProductStatus | None = None


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku: str
    name: str
    description: str | None
    price: Decimal
    category_id: UUID | None
    seller_id: UUID
    stock_quantity: int
    status: ProductStatus
    created_at: datetime
    updated_at: datetime


class ProductSort(StrEnum):
    NEWEST = "newest"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    NAME = "name"


class ProductPage(BaseModel):
    items: list[ProductRead]
    total: int
    page: int
    page_size: int
