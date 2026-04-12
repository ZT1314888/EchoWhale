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


class UnsupportedSceneImageError(ValidationError):
    code = 1007
    status_code = 422
    default_message = "Unsupported scene image"


class SceneAnalysisUnavailableError(EchoWhaleError):
    code = 1008
    status_code = 503
    default_message = "图片分析暂时不可用，请稍后重试。"


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


class AuthenticationError(EchoWhaleError):
    code = 1002
    status_code = 401
    default_message = "Authentication required"


class PermissionDeniedError(EchoWhaleError):
    code = 1003
    status_code = 403
    default_message = "Permission denied"


class ConfigurationError(EchoWhaleError):
    code = 1005
    status_code = 500
    default_message = "Configuration error"


class TooManyRequestsError(EchoWhaleError):
    code = 1006
    status_code = 429
    default_message = "Too many requests"


class ModelProviderError(EchoWhaleError):
    code = 1005
    status_code = 502
    default_message = "Model provider error"


class VoiceTokenError(EchoWhaleError):
    code = 1302
    status_code = 503
    default_message = "Deepgram token 获取失败"


class EmailDeliveryError(EchoWhaleError):
    code = 1005
    status_code = 503
    default_message = "邮件服务暂时不可用，请稍后重试。"


class QueuePublishError(EchoWhaleError):
    code = 1005
    status_code = 503
    default_message = "邮件任务入队失败，请稍后重试。"
