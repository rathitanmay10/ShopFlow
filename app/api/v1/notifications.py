from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUserDep, SessionDep
from app.schemas.notification import NotificationPage
from app.services.notification import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _notification_service(session: SessionDep) -> NotificationService:
    return NotificationService(session)


NotificationServiceDep = Annotated[NotificationService, Depends(_notification_service)]


@router.get("")
async def list_notifications(
    user: CurrentUserDep,
    service: NotificationServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NotificationPage:
    items, total = await service.list_for_user(user.id, page=page, page_size=page_size)
    return NotificationPage(items=items, total=total, page=page, page_size=page_size)
