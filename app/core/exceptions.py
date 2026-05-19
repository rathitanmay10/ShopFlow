from typing import Any


class DomainError(Exception):
    status_code: int = 400
    code: str = "domain_error"

    def __init__(self, message: str, *, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.metadata = metadata or {}


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class PermissionDeniedError(DomainError):
    status_code = 403
    code = "permission_denied"


class AuthenticationError(DomainError):
    status_code = 401
    code = "authentication_failed"


class InvariantViolationError(DomainError):
    status_code = 422
    code = "invariant_violation"


class RateLimitedError(DomainError):
    status_code = 429
    code = "rate_limited"
