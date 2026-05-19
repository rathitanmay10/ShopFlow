from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AnalyticsWindow(StrEnum):
    DAY = "1d"
    WEEK = "7d"
    MONTH = "30d"


class TopProduct(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_id: UUID
    name: str
    units_sold: int
    revenue: Decimal


class SellerPerformance(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    seller_id: UUID
    email: str
    revenue: Decimal
    orders: int


class DailyOrders(BaseModel):
    day: datetime
    count: int
    revenue: Decimal


class AnalyticsSummary(BaseModel):
    window: AnalyticsWindow
    total_revenue: Decimal
    total_orders: int
    active_users: int
    failed_payments: int
    low_stock_count: int
    top_products: list[TopProduct]
    seller_performance: list[SellerPerformance]
    daily_orders: list[DailyOrders]


class UserListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    role: str
    is_active: bool
    created_at: datetime


class UserPage(BaseModel):
    items: list[UserListItem]
    total: int
    page: int
    page_size: int


class AuditLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    actor_id: UUID | None
    action: str
    resource_type: str | None
    resource_id: str | None
    request_id: str | None
    ip: str | None
    metadata_: dict
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogItem]
    total: int
    page: int
    page_size: int
