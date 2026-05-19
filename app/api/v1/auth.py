from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import SessionDep, SettingsDep
from app.repositories.user import UserRepository
from app.schemas.auth import LoginIn, RefreshIn, TokenPair, UserCreate, UserRead
from app.services.auth import AuthService

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
async def login(payload: LoginIn, service: AuthServiceDep) -> TokenPair:
    return await service.login(payload)


@router.post("/refresh")
async def refresh(payload: RefreshIn, service: AuthServiceDep) -> TokenPair:
    return await service.refresh(payload.refresh_token)
