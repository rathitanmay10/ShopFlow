from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.audit_log import AuditLog
from app.models.order import Order, OrderItem, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.product import Product
from app.models.user import User
from app.schemas.analytics import (
    AnalyticsSummary,
    AnalyticsWindow,
    AuditLogItem,
    AuditLogPage,
    DailyOrders,
    SellerPerformance,
    TopProduct,
    UserListItem,
    UserPage,
)

_WINDOW_DAYS: dict[AnalyticsWindow, int] = {
    AnalyticsWindow.DAY: 1,
    AnalyticsWindow.WEEK: 7,
    AnalyticsWindow.MONTH: 30,
}

_REVENUE_STATUSES = [
    OrderStatus.CONFIRMED,
    OrderStatus.SHIPPED,
    OrderStatus.DELIVERED,
]


class AnalyticsService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def summary(self, window: AnalyticsWindow) -> AnalyticsSummary:
        since = datetime.now(UTC) - timedelta(days=_WINDOW_DAYS[window])

        total_revenue = (
            await self.session.execute(
                select(func.coalesce(func.sum(Order.total), 0)).where(
                    Order.status.in_(_REVENUE_STATUSES),
                    Order.created_at >= since,
                )
            )
        ).scalar_one() or Decimal("0")

        total_orders = (
            await self.session.execute(
                select(func.count(Order.id)).where(Order.created_at >= since)
            )
        ).scalar_one()

        active_users = (
            await self.session.execute(
                select(func.count(func.distinct(Order.customer_id))).where(
                    Order.created_at >= since
                )
            )
        ).scalar_one()

        failed_payments = (
            await self.session.execute(
                select(func.count(Payment.id)).where(
                    Payment.status == PaymentStatus.FAILED,
                    Payment.created_at >= since,
                )
            )
        ).scalar_one()

        low_stock_count = (
            await self.session.execute(
                select(func.count(Product.id)).where(
                    Product.deleted_at.is_(None),
                    Product.stock_quantity <= self.settings.low_stock_threshold,
                )
            )
        ).scalar_one()

        top_products_rows = (
            await self.session.execute(
                select(
                    OrderItem.product_id,
                    Product.name,
                    func.sum(OrderItem.quantity).label("units"),
                    func.sum(OrderItem.quantity * OrderItem.unit_price).label("revenue"),
                )
                .join(Order, OrderItem.order_id == Order.id)
                .join(Product, OrderItem.product_id == Product.id)
                .where(
                    Order.created_at >= since,
                    Order.status.in_(_REVENUE_STATUSES),
                )
                .group_by(OrderItem.product_id, Product.name)
                .order_by(func.sum(OrderItem.quantity).desc())
                .limit(10)
            )
        ).all()

        seller_rows = (
            await self.session.execute(
                select(
                    Product.seller_id,
                    User.email,
                    func.coalesce(func.sum(OrderItem.quantity * OrderItem.unit_price), 0).label(
                        "revenue"
                    ),
                    func.count(func.distinct(Order.id)).label("orders"),
                )
                .join(OrderItem, OrderItem.product_id == Product.id)
                .join(Order, OrderItem.order_id == Order.id)
                .join(User, User.id == Product.seller_id)
                .where(
                    Order.created_at >= since,
                    Order.status.in_(_REVENUE_STATUSES),
                )
                .group_by(Product.seller_id, User.email)
                .order_by(func.sum(OrderItem.quantity * OrderItem.unit_price).desc())
                .limit(10)
            )
        ).all()

        daily_rows = (
            await self.session.execute(
                select(
                    func.date_trunc("day", Order.created_at).label("day"),
                    func.count(Order.id).label("order_count"),
                    func.coalesce(func.sum(Order.total), 0).label("revenue"),
                )
                .where(Order.created_at >= since)
                .group_by("day")
                .order_by("day")
            )
        ).all()

        return AnalyticsSummary(
            window=window,
            total_revenue=Decimal(total_revenue),
            total_orders=total_orders,
            active_users=active_users,
            failed_payments=failed_payments,
            low_stock_count=low_stock_count,
            top_products=[
                TopProduct(
                    product_id=row.product_id,
                    name=row.name,
                    units_sold=int(row.units),
                    revenue=Decimal(row.revenue),
                )
                for row in top_products_rows
            ],
            seller_performance=[
                SellerPerformance(
                    seller_id=row.seller_id,
                    email=row.email,
                    revenue=Decimal(row.revenue),
                    orders=int(row.orders),
                )
                for row in seller_rows
            ],
            daily_orders=[
                DailyOrders(
                    day=row.day,
                    count=int(row.order_count),
                    revenue=Decimal(row.revenue),
                )
                for row in daily_rows
            ],
        )

    async def list_users(self, *, page: int, page_size: int) -> UserPage:
        stmt = select(User).order_by(User.created_at.desc())
        total = (
            await self.session.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        rows = (
            (await self.session.execute(stmt.offset((page - 1) * page_size).limit(page_size)))
            .scalars()
            .all()
        )
        return UserPage(
            items=[
                UserListItem(
                    id=u.id,
                    email=u.email,
                    role=u.role.value,
                    is_active=u.is_active,
                    created_at=u.created_at,
                )
                for u in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def list_audit_logs(
        self, *, page: int, page_size: int, action: str | None = None
    ) -> AuditLogPage:
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
        if action:
            stmt = stmt.where(AuditLog.action == action)
        total = (
            await self.session.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        rows = (
            (await self.session.execute(stmt.offset((page - 1) * page_size).limit(page_size)))
            .scalars()
            .all()
        )
        return AuditLogPage(
            items=[
                AuditLogItem(
                    id=r.id,
                    actor_id=r.actor_id,
                    action=r.action,
                    resource_type=r.resource_type,
                    resource_id=r.resource_id,
                    request_id=r.request_id,
                    ip=r.ip,
                    metadata_=r.metadata_,
                    created_at=r.created_at,
                )
                for r in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
