import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq.connections import RedisSettings, create_pool
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_v1
from app.core.config import get_settings
from app.core.exceptions import DomainError
from app.core.logging import configure_logging
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    try:
        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    except Exception:
        logger.warning("arq_pool_unavailable_on_startup", exc_info=True)
        pool = None
    app.state.arq_pool = pool
    try:
        yield
    finally:
        if pool is not None:
            await pool.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="ShopFlow API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(DomainError)
    async def _domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "metadata": exc.metadata,
                }
            },
        )

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_v1)
    return app


app = create_app()
