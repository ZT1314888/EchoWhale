from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import text

from api.common.exceptions import EchoWhaleError
from api.common.middleware import (
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
    TracingMiddleware,
)
from api.common.request_context import configure_request_id_logging
from api.common.responses import ApiResponse
from api.common.telemetry import configure_telemetry
from api.core.config import settings
from api.db.database import get_async_session_factory
from api.routes.v1 import router as v1_router

logger = logging.getLogger(__name__)

# request id 日志接入放在模块导入期：此后所有 api.* 日志经 root handler 的
# filter 自动携带请求上下文 id，无需逐点修改既有 logger.xxx 调用。
configure_request_id_logging()

# OTel 链路追踪装配（幂等；默认关闭态是 no-op，零行为）。开启态经 OTLP HTTP
# 导出，标准 OTEL_* 环境变量由 SDK 原生消费，见 docs/observability.md。
configure_telemetry()

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

# server span 中间件挂最内层（第一个 add = 最内层，request-id 之内）：进入时
# request-id ContextVar 已建立，server span 可直接携带关联 id；探针路径旁路。
app.add_middleware(TracingMiddleware)

# request-id 中间件次内层。有意为之的取舍：body 门 413 拒绝发生在 request-id
# 上下文建立之前，因此 413 响应不带 X-Request-ID——拒绝发生在上下文注入之前，
# 属于可接受的盲区（design 第 5 节）。
app.add_middleware(RequestContextMiddleware)

# 请求管线顺序为 CORS → 请求体大小门 → request-id → tracing → 路由：Starlette 的
# add_middleware 后添加者在最外层，因此先挂 body 门再挂 CORS，超限 413 响应才会经
# CORS 包裹带上跨域头，浏览器端前端才能读到统一信封而不是裸网络错误。
app.add_middleware(BodySizeLimitMiddleware)

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


# ---------- /readyz 就绪探针（语义与 /health 的区别见 design 第 3 节） ----------
#
# /health 是 liveness（进程活着，永不动探针），/readyz 是 readiness（依赖可用，
# 不ready 时基础设施把实例摘出流量）。探针的消费方是 LB / K8s 等基础设施而非
# 前端 ApiResponse 解析器，因此返回轻量 JSON，不走统一信封。
# 每次请求实时探测、无缓存：探针频率由基础设施的探针间隔控制，应用不做节流。
# 探针函数保持模块级并作为 Depends provider：测试用 dependency_overrides 注入
# 替身，绝不发真实网络请求。


async def probe_database() -> str:
    """DB 探针：SELECT 1 实测连通性（真实网络语义，失败即 down）。"""
    try:
        async with get_async_session_factory()() as session:
            await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - 探针把一切异常归一为 down，503 不能变成 500
        return "down"
    return "up"


async def probe_redis() -> str:
    """Redis 探针：未配置时跳过（开发宽容，生产清单要求 Redis），配置了才实测 PING。"""
    if not settings.redis_url.strip():
        return "unconfigured"
    client = Redis.from_url(
        settings.redis_url,
        # 探针自带硬超时：redis 客户端默认 socket_timeout=None 会无限阻塞，
        # 探针挂起比探针失败更糟（基础设施会一直等）。不新增配置项，超时写死。
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        await asyncio.to_thread(client.ping)
    except Exception:  # noqa: BLE001 - 同 DB 探针：失败即 down，不上抛
        return "down"
    else:
        return "up"
    finally:
        # close 失败不影响探针结论；连接未建立时 close 是无害的空操作。
        with contextlib.suppress(Exception):
            await asyncio.to_thread(client.close)


async def probe_r2_config() -> str:
    """R2 探针只查配置齐备性、零网络：真实探测会产生 S3 费用与慢超时，不值得。

    与 Redis 同一宽容逻辑：missing 只在开发环境出现（生产门控在启动时已强制
    R2 三凭证），不参与 ready 判定；真实上传路径的故障由业务错误日志暴露。
    """
    configured = all(
        (
            settings.r2_endpoint.strip(),
            settings.r2_access_key_id.strip(),
            settings.r2_secret_access_key.strip(),
        )
    )
    return "configured" if configured else "missing"


@app.get("/readyz")
async def readyz(
    db_status: str = Depends(probe_database),
    redis_status: str = Depends(probe_redis),
    r2_status: str = Depends(probe_r2_config),
) -> JSONResponse:
    checks = {"db": db_status, "redis": redis_status, "r2": r2_status}
    # 只有实测失败（down）才算 unready；unconfigured / missing 是"未部署"而非
    # "坏了"，与开发环境无 Redis / 无 R2 的现实一致。
    unready = db_status == "down" or redis_status == "down"
    return JSONResponse(
        content={"status": "unready" if unready else "ready", "checks": checks},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE if unready else status.HTTP_200_OK,
    )
