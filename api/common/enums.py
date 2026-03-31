from enum import Enum


class SessionStatus(str, Enum):
    draft = "draft"
    active = "active"
    completed = "completed"
