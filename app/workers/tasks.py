import logging
from typing import Any
from uuid import UUID

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.exceptions import InvariantViolationError, NotFoundError
from app.core.logging import configure_logging
from app.db import async_session_maker, engine
from app.models.notification import NotificationChannel
from app.repositories.order import OrderRepository
from app.services.inventory import InventoryService
from app.services.notification import NotificationService
from app.services.order import OrderService
from app.services.payment import PaymentService, PaymentSimulationError

logger = logging.getLogger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    ctx["settings"] = settings


async def shutdown(_ctx: dict[str, Any]) -> None:
    await engine.dispose()


async def process_payment(ctx: dict[str, Any], order_id: str) -> None:
    settings = ctx["settings"]
    arq_pool = ctx.get("redis")
    job_try = ctx.get("job_try", 1)
    is_terminal = job_try >= WorkerSettings.max_tries

    async with async_session_maker() as session:
        try:
            await PaymentService(session, settings, arq_pool=arq_pool).process(UUID(order_id))
            await session.commit()
            return
        except (NotFoundError, InvariantViolationError) as exc:
            await session.rollback()
            logger.warning(
                "process_payment terminal skip",
                extra={"ctx_order_id": order_id, "ctx_reason": str(exc)},
            )
            return
        except PaymentSimulationError:
            # Persist the FAILED event + attempts increment + PENDING reset so retries
            # see fresh state. Without this commit, the rollback at context exit would
            # discard the increment and `payment.attempts` would stay at 0.
            await session.commit()
            if not is_terminal:
                raise

    # Terminal: ARQ has exhausted retries. Cancel the order and restore stock so the
    # customer's hold is released. Otherwise the order is stuck in PENDING with stock
    # still decremented.
    async with async_session_maker() as session:
        inventory = InventoryService(session, settings, arq_pool=arq_pool)
        order_service = OrderService(session, OrderRepository(session), inventory, settings)
        try:
            await order_service.system_cancel(UUID(order_id))
            await session.commit()
            logger.warning(
                "payment_terminal_cancel",
                extra={"ctx_order_id": order_id, "ctx_attempts": job_try},
            )
        except (NotFoundError, InvariantViolationError) as exc:
            await session.rollback()
            logger.warning(
                "payment_terminal_cancel_skipped",
                extra={"ctx_order_id": order_id, "ctx_reason": str(exc)},
            )


async def send_notification(
    _ctx: dict[str, Any],
    user_id: str,
    channel: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    async with async_session_maker() as session:
        await NotificationService(session).send(
            UUID(user_id), NotificationChannel(channel), event_type, payload
        )
        await session.commit()


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    on_startup = startup
    on_shutdown = shutdown
    functions = (process_payment, send_notification)
    max_tries = 4
    retry_delay = 5
