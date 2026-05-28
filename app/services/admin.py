from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.user import UserRepository
from app.services.audit import AuditService


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._users = UserRepository(session)
        self._audit = AuditService(session)

    async def suspend_user(self, user_id: UUID, *, suspend: bool, actor_id: UUID) -> bool:
        active = not suspend
        if not await self._users.set_active(user_id, active=active):
            raise NotFoundError("user_not_found")
        action = "user_suspended" if suspend else "user_unsuspended"
        await self._audit.record(
            action,
            actor_id=actor_id,
            resource_type="user",
            resource_id=str(user_id),
        )
        return active
