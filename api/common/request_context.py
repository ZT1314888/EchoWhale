"""请求关联 ID（request id）基建：ContextVar、入站校验/生成、日志 filter。

为什么放 ContextVar 而不是 request.state：异步多轮链路（反馈 + 教练 + 流式 + 落库）
里的日志调用大多发生在 request 对象够不着的层（引擎 / 仓储 / 任务），ContextVar
是唯一能把"同一请求"身份贯穿到任意 await 深处的机制。
"""

from __future__ import annotations

import logging
import secrets
from contextvars import ContextVar, Token
from typing import Any

# ASGI scope 里的头名恒为小写 bytes，响应头也统一用小写写入。
REQUEST_ID_HEADER = "x-request-id"
# 入站 X-Request-ID 的最大可信长度：超长值可能是注入或脏数据，直接丢弃重新生成。
MAX_INBOUND_REQUEST_ID_LENGTH = 64
# 无请求上下文（启动期 / 后台任务）时的日志占位符，保证 %(request_id)s 恒有值。
MISSING_REQUEST_ID = "-"

_request_id_var: ContextVar[str | None] = ContextVar("echowhale_request_id", default=None)


def get_request_id() -> str | None:
    """取当前请求的关联 id；无请求上下文时返回 None。"""
    return _request_id_var.get()


def set_request_id(request_id: str) -> Token[str | None]:
    """建立请求上下文（由 RequestContextMiddleware 调用），返回 token 供请求结束后复位。"""
    return _request_id_var.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """请求结束复位 ContextVar，避免 id 泄漏到同线程后续的无请求上下文日志。"""
    _request_id_var.reset(token)


def generate_request_id() -> str:
    """生成 `req_<16hex>` 形态的新 id。

    关联用途而已，不是安全凭据：随机 hex 足以在部署窗口内唯一标识一次请求，
    不需要时间戳前缀（design 第 2 节：保持简单）。
    """
    return f"req_{secrets.token_hex(8)}"


def is_reusable_request_id(value: str) -> bool:
    """入站 id 是否可复用：非空、不超过 64 字符、ASCII 且可打印。

    不信任客户端：控制字符会污染日志行，超长值会撑爆日志存储，一律重新生成。
    """
    return (
        bool(value)
        and len(value) <= MAX_INBOUND_REQUEST_ID_LENGTH
        and value.isascii()
        and value.isprintable()
    )


def ensure_request_id(scope: dict[str, Any]) -> str:
    """从 ASGI scope 读入站 X-Request-ID：合法则复用，缺失 / 不合法则生成新 id。

    只看首个同名头，首个不合法就不再翻后续同名头——重复头本身就是可疑信号。
    """
    for name, raw_value in scope.get("headers") or []:
        if name == REQUEST_ID_HEADER.encode("latin-1"):
            candidate = raw_value.decode("latin-1").strip()
            if is_reusable_request_id(candidate):
                return candidate
            break
    return generate_request_id()


class RequestIdFilter(logging.Filter):
    """把 ContextVar 里的 request id 注入每条日志记录（缺失时占位 `-`）。

    为什么挂 handler 而不是 root logger：Logger 级 filter 只作用于直接经由该
    logger 发出的记录，`api.*` 子 logger 传播上来的记录会绕过它；handler 级
    filter 对抵达该 handler 的所有记录生效，全仓日志才能统一带上 id。
    本 filter 只负责把属性放上记录，是否出现在输出里由各 handler 的格式串决定。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or MISSING_REQUEST_ID
        return True


def configure_request_id_logging() -> None:
    """把 RequestIdFilter 挂到 root logger 的每个 handler 上（幂等，main.py 启动时调用）。

    root 尚无 handler 时用 basicConfig 补一个带 `%(request_id)s` 的格式串；
    root 已有 handler（宿主 / 测试环境预配置，如 uvicorn 托管日志）时保持
    no-op——不动别人已有的格式串，只追加 filter，保证 record.request_id
    属性恒在，留给未来的 JSON 格式器直接消费。
    """
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            format="%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s",
        )
    request_id_filter = RequestIdFilter()
    for handler in root.handlers:
        if not any(isinstance(existing, RequestIdFilter) for existing in handler.filters):
            handler.addFilter(request_id_filter)
