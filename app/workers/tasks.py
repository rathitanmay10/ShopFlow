import logging
from typing import Any
from uuid import UUID

from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.notification import NotificationService
from app.services.payment import PaymentService

logger = logging.getLogger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    ctx["settings"] = settings
    ctx["engine"] = engine
    ctx["session_factory"] = async_sessionmaker(engine, expire_on_commit=False)


async def shutdown(ctx: dict[str, Any]) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


async def process_payment(ctx: dict[str, Any], order_id: str) -> None:
    settings = ctx["settings"]
    factory = ctx["session_factory"]
    async with factory() as session:
        service = PaymentService(session, settings)
        await service.process(UUID(order_id))
        await session.commit()


async def send_email(
    ctx: dict[str, Any], user_id: str, event_type: str, payload: dict[str, Any]
) -> None:
    factory = ctx["session_factory"]
    async with factory() as session:
        await NotificationService(session).send(UUID(user_id), "email", event_type, payload)
        await session.commit()


async def send_sms(
    ctx: dict[str, Any], user_id: str, event_type: str, payload: dict[str, Any]
) -> None:
    factory = ctx["session_factory"]
    async with factory() as session:
        await NotificationService(session).send(UUID(user_id), "sms", event_type, payload)
        await session.commit()


async def create_in_app(
    ctx: dict[str, Any], user_id: str, event_type: str, payload: dict[str, Any]
) -> None:
    factory = ctx["session_factory"]
    async with factory() as session:
        await NotificationService(session).send(UUID(user_id), "in_app", event_type, payload)
        await session.commit()


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    on_startup = startup
    on_shutdown = shutdown
    functions = (process_payment, send_email, send_sms, create_in_app)
    max_tries = 4
    retry_delay = 5
