from __future__ import annotations

from fastapi.routing import APIRoute

from api.main import app

DEEPGRAM_THINK_PATH_SUFFIX = "/deepgram/think/chat/completions"


def _deepgram_think_path() -> str:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.endswith(DEEPGRAM_THINK_PATH_SUFFIX):
            return route.path
    raise AssertionError("deepgram think route is not registered")


def test_openapi_schema_generates_for_all_routes() -> None:
    schema = app.openapi()

    assert schema["openapi"].startswith("3.")
    assert _deepgram_think_path() in schema["paths"]


def test_deepgram_think_route_does_not_leak_session_factory_param() -> None:
    schema = app.openapi()

    parameters = schema["paths"][_deepgram_think_path()]["post"].get("parameters") or []
    leaked = [param["name"] for param in parameters if param["name"] == "session_factory"]
    assert leaked == []
