import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


async def get_redis_or_none(url: str, *, ctx: str) -> Redis | None:
    """Open a Redis client, ping to verify reachability. Returns None on failure.

    `ctx` is included in the warning log so callers (rate limiter, login throttle,
    ARQ enqueue, etc.) are distinguishable in logs.
    """
    try:
        client = Redis.from_url(url, decode_responses=True)
        await client.ping()
    except RedisError:
        logger.warning("redis_unavailable", extra={"ctx": ctx}, exc_info=True)
        return None
    return client
