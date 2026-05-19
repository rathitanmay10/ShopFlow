from app.core.config import Settings
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import (
    TokenType,
    create_token,
    decode_token,
    hash_password,
    subject_uuid,
    verify_password,
)
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import LoginIn, TokenPair, UserCreate


class AuthService:
    def __init__(self, users: UserRepository, settings: Settings) -> None:
        self.users = users
        self.settings = settings

    async def register(self, payload: UserCreate) -> User:
        if await self.users.get_by_email(payload.email):
            raise ConflictError("email_already_registered")
        user = User(
            email=payload.email,
            password_hash=hash_password(payload.password.get_secret_value()),
            role=payload.role,
        )
        return await self.users.create(user)

    async def login(self, payload: LoginIn) -> TokenPair:
        user = await self.users.get_by_email(payload.email)
        if user is None or not verify_password(
            payload.password.get_secret_value(), user.password_hash
        ):
            raise AuthenticationError("invalid_credentials")
        if not user.is_active:
            raise AuthenticationError("user_inactive")
        return self._issue_tokens(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        payload = decode_token(self.settings, refresh_token, TokenType.REFRESH)
        user = await self.users.get_by_id(subject_uuid(payload))
        if user is None or not user.is_active:
            raise AuthenticationError("user_inactive")
        return self._issue_tokens(user)

    def _issue_tokens(self, user: User) -> TokenPair:
        extra = {"role": user.role.value}
        return TokenPair(
            access_token=create_token(self.settings, str(user.id), TokenType.ACCESS, extra),
            refresh_token=create_token(self.settings, str(user.id), TokenType.REFRESH),
        )
