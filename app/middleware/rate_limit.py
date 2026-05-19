import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.core.redis_client import get_redis_or_none


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window per-IP rate limit using a Redis INCR with TTL.

    Skips when Redis is unreachable (greenfield mode logs and lets the request through).
    Per-route auth throttle lives in `app.services.login_throttle` and is called from
    the auth endpoints directly.
    """

    def __init__(self, app, *, redis_url: str | None = None, limit: int | None = None) -> None:
        super().__init__(app)
        settings = get_settings()
        self._redis_url = redis_url or settings.redis_url
        self._limit = limit or settings.rate_limit_default_per_min
        self._client: Redis | None = None

    async def _get_client(self) -> Redis | None:
        if self._client is None:
            self._client = await get_redis_or_none(self._redis_url, ctx="rate_limit")
        return self._client

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        client = await self._get_client()
        if client is None:
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        window = int(time.time() // 60)
        key = f"rl:{ip}:{window}"
        try:
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, 70)
        except RedisError:
            return await call_next(request)
        if count > self._limit:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "too_many_requests",
                        "metadata": {"limit": self._limit, "window_seconds": 60},
                    }
                },
            )
        return await call_next(request)
