from typing import Any


def success(data: Any, message: str = "ok") -> dict[str, Any]:
    return {"success": True, "message": message, "data": data}
