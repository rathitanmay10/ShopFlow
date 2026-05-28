import logging
from typing import Any
from uuid import UUID

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.exceptions import InvariantViolationError, NotFoundError
from app.core.logging import configure_logging
from app.db import async_session_maker, engine
from app.models.notification import NotificationChannel
from app.services.notification import NotificationService
from app.services.payment import PaymentService

logger = logging.getLogger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    ctx["settings"] = settings


async def shutdown(_ctx: dict[str, Any]) -> None:
    await engine.dispose()


async def process_payment(ctx: dict[str, Any], order_id: str) -> None:
    settings = ctx["settings"]
    async with async_session_maker() as session:
        try:
            await PaymentService(session, settings).process(UUID(order_id))
            await session.commit()
        except (NotFoundError, InvariantViolationError) as exc:
            logger.warning("process_payment terminal skip", extra={"ctx_order_id": order_id, "ctx_reason": str(exc)})
            return


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
