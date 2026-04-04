from __future__ import annotations

from typing import Any


class EchoWhaleError(Exception):
    """Base application error."""

    code = 1005
    status_code = 500
    default_message = "Application error"

    def __init__(self, message: str | None = None, *, data: Any = None) -> None:
        self.message = message or self.default_message
        self.data = data
        super().__init__(self.message)


class NotFoundError(EchoWhaleError):
    """Raised when an entity does not exist."""

    code = 1004
    status_code = 404
    default_message = "Resource not found"


class ValidationError(EchoWhaleError):
    """Raised when user input is invalid."""

    code = 1001
    status_code = 400
    default_message = "Validation error"


class UnsupportedMediaTypeError(ValidationError):
    status_code = 415
    default_message = "Unsupported media type"


class FileTooLargeError(ValidationError):
    status_code = 413
    default_message = "File too large"


class InvalidStateError(EchoWhaleError):
    code = 1001
    status_code = 409
    default_message = "Invalid state"


class StorageError(EchoWhaleError):
    code = 1005
    status_code = 502
    default_message = "Storage error"


class ConfigurationError(EchoWhaleError):
    code = 1005
    status_code = 500
    default_message = "Configuration error"
