"""Application-level exception hierarchy.

:class:`AppException` is the base for all business-logic errors that should be
translated into a structured JSON response by the global exception handler
registered in ``app/main.py``. Subclasses set a sensible default ``status_code``
and ``error_code``; callers may override per-instance.

Exception hierarchy::

    AppException (400, ERR_APP)
    ├── ValidationError (422, ERR_VALIDATION)
    ├── AuthenticationError (401, ERR_AUTHENTICATION)
    ├── PermissionError (403, ERR_PERMISSION_DENIED)
    ├── NotFoundError (404, ERR_NOT_FOUND)
    ├── ConflictException (409, ERR_CONFLICT)
    └── BusinessError (400, ERR_BUSINESS)

Backward-compatible aliases (kept for existing code that uses the *Exception naming):
    - ValidationException → ValidationError
    - PermissionDeniedException → PermissionError
    - NotFoundException → NotFoundError
"""
from __future__ import annotations

from typing import Any


class AppException(Exception):
    """Base application exception rendered as a structured JSON response.

    Attributes:
        status_code: HTTP status code to return.
        error_code:  Stable machine-readable error code (e.g. ``"ERR_DEVICE_OFFLINE"``).
        message:     Human-readable message.
        details:     Optional opaque payload (dict) with extra context.
    """

    status_code: int = 400
    error_code: str = "ERR_APP"

    def __init__(
        self,
        message: str = "",
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Internal helper:   init  ."""
        super().__init__(message or self.error_code)
        self.message = message or self.error_code
        if status_code is not None:
            self.status_code = status_code
        if error_code is not None:
            self.error_code = error_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the JSON body returned by the exception handler."""
        payload: dict[str, Any] = {
            "detail": self.message,
            "message": self.message,
            "status_code": self.status_code,
            "error_code": self.error_code,
        }
        if self.details:
            payload["details"] = self.details
        return payload

    def __repr__(self) -> str:
        """Internal helper:   repr  ."""
        return f"{type(self).__name__}(status_code={self.status_code}, error_code={self.error_code!r}, message={self.message!r})"


# --- Primary exception hierarchy (use these in new code) ---------------------

class ValidationError(AppException):
    """请求参数校验失败（422）。"""
    status_code = 422
    error_code = "ERR_VALIDATION"


class AuthenticationError(AppException):
    """认证失败：token 无效/过期/未提供（401）。"""
    status_code = 401
    error_code = "ERR_AUTHENTICATION"


class PermissionError(AppException):  # noqa: A001 — intentionally shadows builtin for domain clarity
    """鉴权失败：用户无权限访问该资源（403）。"""
    status_code = 403
    error_code = "ERR_PERMISSION_DENIED"


class NotFoundError(AppException):
    """请求的资源不存在（404）。"""
    status_code = 404
    error_code = "ERR_NOT_FOUND"


class BusinessError(AppException):
    """业务逻辑错误：状态机非法转换、前置条件不满足等（400）。"""
    status_code = 400
    error_code = "ERR_BUSINESS"


class ConflictException(AppException):
    """资源状态冲突（409）。"""
    status_code = 409
    error_code = "ERR_CONFLICT"


# --- Backward-compatible aliases (existing code may use these names) ----------

ValidationException = ValidationError
PermissionDeniedException = PermissionError
NotFoundException = NotFoundError


__all__ = [
    "AppException",
    "ValidationError",
    "AuthenticationError",
    "PermissionError",
    "NotFoundError",
    "BusinessError",
    "ConflictException",
    # Backward-compatible aliases
    "ValidationException",
    "PermissionDeniedException",
    "NotFoundException",
]

