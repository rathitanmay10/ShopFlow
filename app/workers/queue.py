import logging
from typing import Any

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import Settings

logger = logging.getLogger(__name__)


async def enqueue(
    settings: Settings,
    task_name: str,
    *args: Any,
    pool: ArqRedis | None = None,
    **kwargs: Any,
) -> bool:
    """Best-effort enqueue. Returns False if Redis is unreachable.

    If `pool` is passed, reuses it (set up in FastAPI lifespan or provided
    by ARQ worker via `ctx['redis']`). Otherwise creates and closes a
    fresh pool for this single enqueue call.
    """
    if pool is not None:
        try:
            await pool.enqueue_job(task_name, *args, **kwargs)
            return True
        except Exception:
            logger.warning(
                "arq_enqueue_failed",
                extra={"ctx_task": task_name},
                exc_info=True,
            )
            return False

    try:
        own_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    except Exception:
        logger.warning(
            "arq_pool_unavailable",
            extra={"ctx_task": task_name},
            exc_info=True,
        )
        return False
    try:
        await own_pool.enqueue_job(task_name, *args, **kwargs)
        return True
    finally:
        await own_pool.aclose()
