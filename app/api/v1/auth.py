from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import SessionDep, SettingsDep
from app.core.exceptions import AuthenticationError
from app.repositories.user import UserRepository
from app.schemas.auth import LoginIn, RefreshIn, TokenPair, UserCreate, UserRead
from app.services.auth import AuthService
from app.services.login_throttle import LoginThrottle

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_service(session: SessionDep, settings: SettingsDep) -> AuthService:
    return AuthService(UserRepository(session), settings)


AuthServiceDep = Annotated[AuthService, Depends(_auth_service)]


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate,
    service: AuthServiceDep,
    session: SessionDep,
) -> UserRead:
    user = await service.register(payload)
    await session.commit()
    return UserRead.model_validate(user)


@router.post("/login")
async def login(
    payload: LoginIn,
    request: Request,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> TokenPair:
    ip = request.client.host if request.client else "unknown"
    throttle = LoginThrottle(settings)
    await throttle.check(ip, payload.email)
    try:
        tokens = await service.login(payload)
    except AuthenticationError:
        await throttle.record_failure(ip, payload.email)
        raise
    await throttle.record_success(ip, payload.email)
    return tokens


@router.post("/refresh")
async def refresh(payload: RefreshIn, service: AuthServiceDep) -> TokenPair:
    return await service.refresh(payload.refresh_token)
