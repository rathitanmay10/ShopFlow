from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import SessionDep, SettingsDep, require_role
from app.core.exceptions import NotFoundError
from app.models.user import UserRole
from app.repositories.user import UserRepository
from app.schemas.analytics import (
    AnalyticsSummary,
    AnalyticsWindow,
    AuditLogPage,
    UserPage,
)
from app.services.analytics import AnalyticsService

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)


class SuspendIn(BaseModel):
    suspend: bool


def _analytics_service(session: SessionDep, settings: SettingsDep) -> AnalyticsService:
    return AnalyticsService(session, settings)


AnalyticsServiceDep = Annotated[AnalyticsService, Depends(_analytics_service)]


@router.get("/analytics")
async def analytics(
    service: AnalyticsServiceDep,
    window: Annotated[AnalyticsWindow, Query()] = AnalyticsWindow.WEEK,
) -> AnalyticsSummary:
    return await service.summary(window)


@router.get("/users")
async def list_users(
    service: AnalyticsServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> UserPage:
    return await service.list_users(page=page, page_size=page_size)


@router.patch("/users/{user_id}/suspend")
async def suspend_user(user_id: UUID, payload: SuspendIn, session: SessionDep) -> dict[str, bool]:
    active = not payload.suspend
    if not await UserRepository(session).set_active(user_id, active=active):
        raise NotFoundError("user_not_found")
    await session.commit()
    return {"is_active": active}


@router.get("/audit-logs")
async def list_audit_logs(
    service: AnalyticsServiceDep,
    action: Annotated[str | None, Query(max_length=64)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditLogPage:
    return await service.list_audit_logs(page=page, page_size=page_size, action=action)
