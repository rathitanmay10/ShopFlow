from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import TokenType, decode_token, subject_uuid
from app.db import get_async_session
from app.models.user import User, UserRole
from app.repositories.user import UserRepository

SessionDep = Annotated[AsyncSession, Depends(get_async_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("missing_token")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_token(settings, token, TokenType.ACCESS)
    user = await UserRepository(session).get_by_id(subject_uuid(payload))
    if user is None or not user.is_active:
        raise AuthenticationError("user_inactive")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def require_role(*roles: UserRole) -> Callable[[User], Coroutine[Any, Any, User]]:
    async def _checker(user: CurrentUserDep) -> User:
        if user.role not in roles:
            raise PermissionDeniedError(
                "insufficient_role",
                metadata={"required": [r.value for r in roles]},
            )
        return user

    return _checker
