import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.exceptions import RateLimitedError

logger = logging.getLogger(__name__)


class LoginThrottle:
    """Throttle failed login attempts by IP+email.

    `check` raises `RateLimitedError` if the bucket is exhausted.
    `record_failure` / `record_success` are called by AuthService after each attempt.
    Falls open (no throttling) when Redis is unreachable, with a warning log.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Redis | None = None

    async def _client_or_none(self) -> Redis | None:
        if self._client is not None:
            return self._client
        try:
            self._client = Redis.from_url(self.settings.redis_url, decode_responses=True)
            await self._client.ping()
        except RedisError:
            logger.warning("login_throttle_redis_unavailable", exc_info=True)
            self._client = None
        return self._client

    @staticmethod
    def _key(ip: str, email: str) -> str:
        return f"login_fail:{ip}:{email.lower()}"

    async def check(self, ip: str, email: str) -> None:
        client = await self._client_or_none()
        if client is None:
            return
        try:
            raw = await client.get(self._key(ip, email))
        except RedisError:
            return
        count = int(raw) if raw else 0
        if count >= self.settings.rate_limit_auth_per_min:
            raise RateLimitedError(
                "too_many_failed_logins",
                metadata={"limit": self.settings.rate_limit_auth_per_min},
            )

    async def record_failure(self, ip: str, email: str) -> None:
        client = await self._client_or_none()
        if client is None:
            return
        try:
            count = await client.incr(self._key(ip, email))
            if count == 1:
                await client.expire(self._key(ip, email), 60)
        except RedisError:
            return

    async def record_success(self, ip: str, email: str) -> None:
        client = await self._client_or_none()
        if client is None:
            return
        try:
            await client.delete(self._key(ip, email))
        except RedisError:
            return
