from __future__ import annotations


USER_OWNER_PREFIX = "user:"
VISITOR_OWNER_PREFIX = "visitor:"


def build_user_owner(user_id: str) -> str:
    return f"{USER_OWNER_PREFIX}{user_id}"


def build_visitor_owner(visitor_id: str) -> str:
    return f"{VISITOR_OWNER_PREFIX}{visitor_id}"


def owner_to_storage_path(owner_id: str) -> str:
    if owner_id.startswith(USER_OWNER_PREFIX):
        return f"user/{owner_id.removeprefix(USER_OWNER_PREFIX)}"
    if owner_id.startswith(VISITOR_OWNER_PREFIX):
        return f"visitor/{owner_id.removeprefix(VISITOR_OWNER_PREFIX)}"
    return owner_id
