from enum import Enum


class SessionStatus(str, Enum):
    draft = "draft"
    active = "active"
    completed = "completed"


class MediaUploadStatus(str, Enum):
    pending = "pending"
    uploaded = "uploaded"
    failed = "failed"
