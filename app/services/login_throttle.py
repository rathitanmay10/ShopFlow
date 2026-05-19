from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.exceptions import RateLimitedError
from app.core.redis_client import get_redis_or_none


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
        if self._client is None:
            self._client = await get_redis_or_none(self.settings.redis_url, ctx="login_throttle")
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
        key = self._key(ip, email)
        try:
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, 60)
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
