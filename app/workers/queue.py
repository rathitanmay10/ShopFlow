import logging
from typing import Any

from arq.connections import RedisSettings, create_pool

from app.core.config import Settings

logger = logging.getLogger(__name__)


async def enqueue(settings: Settings, task_name: str, *args: Any, **kwargs: Any) -> bool:
    """Best-effort enqueue. Returns False if Redis is unreachable (greenfield mode).

    Phase 12 will move the ArqRedis pool to FastAPI lifespan and reuse it across requests.
    """
    try:
        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    except Exception:
        logger.warning(
            "arq_pool_unavailable",
            extra={"ctx_task": task_name},
            exc_info=True,
        )
        return False
    try:
        await pool.enqueue_job(task_name, *args, **kwargs)
        return True
    finally:
        await pool.close()
