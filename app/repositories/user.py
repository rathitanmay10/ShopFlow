from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def set_active(self, user_id: UUID, *, active: bool) -> bool:
        """Set `is_active` flag. Returns True if a user row was updated."""
        from sqlalchemy import update

        result = await self.session.execute(
            update(User).where(User.id == user_id).values(is_active=active).returning(User.id)
        )
        return result.scalar_one_or_none() is not None
