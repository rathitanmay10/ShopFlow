import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attaches a request_id to every request, sets `X-Request-ID` response header,
    and emits an access log with method, path, status, latency_ms, request_id."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "request_error",
                extra={
                    "ctx_request_id": request_id,
                    "ctx_method": request.method,
                    "ctx_path": request.url.path,
                    "ctx_latency_ms": round(latency_ms, 2),
                },
            )
            raise
        latency_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_complete",
            extra={
                "ctx_request_id": request_id,
                "ctx_method": request.method,
                "ctx_path": request.url.path,
                "ctx_status": response.status_code,
                "ctx_latency_ms": round(latency_ms, 2),
            },
        )
        return response
