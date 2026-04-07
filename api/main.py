from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from api.common.exceptions import EchoWhaleError
from api.common.responses import ApiResponse
from api.core.config import settings
from api.routes.v1 import router as v1_router


logger = logging.getLogger(__name__)

settings.validate_runtime()
logger.info(
    "Deepgram voice config status: api_key=%s base_url=%s",
    "set" if settings.deepgram_api_key.strip() else "missing",
    "set" if settings.deepgram_agent_base_url.strip() else "missing",
)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="EchoWhale API for scene-based English conversation practice.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix=settings.api_prefix)


@app.exception_handler(EchoWhaleError)
async def echowhale_exception_handler(request: Request, exc: EchoWhaleError):
    logger.error("EchoWhale error on %s %s: %s", request.method, request.url, exc.message)
    return ApiResponse.failed(
        message=exc.message,
        body_code=exc.code,
        http_code=exc.status_code,
        data=exc.data,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error("HTTP error on %s %s: %s", request.method, request.url, exc.detail)
    message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    data = None if isinstance(exc.detail, str) else exc.detail
    return ApiResponse.failed(
        message=message,
        body_code=exc.status_code,
        http_code=exc.status_code,
        data=data,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("Validation error on %s %s: %s", request.method, request.url, exc.errors())
    return ApiResponse.failed(
        message="Validation error",
        body_code=1001,
        http_code=status.HTTP_400_BAD_REQUEST,
        data=exc.errors(),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url)
    return ApiResponse.failed(
        message="Internal server error",
        body_code=1005,
        http_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
