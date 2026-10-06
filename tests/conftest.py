from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def span_exporter():
    """内存导出器：收集测试期间结束的 span，teardown 清空防跨用例泄漏。"""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    yield exporter
    exporter.clear()


@pytest.fixture
def recording_tracer(monkeypatch: pytest.MonkeyPatch, span_exporter):
    """把 telemetry._tracer 整体替换为独立 SDK TracerProvider 产出的 tracer。

    隔离铁律（design 2.5）：绝不调用 trace.set_tracer_provider()——全局 provider
    只服务自动插桩且只能设一次；这里构建私有 provider + SimpleSpanProcessor +
    InMemorySpanExporter，monkeypatch 换掉模块级 _tracer，测试结束自动恢复。
    """
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    from api.common import telemetry

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer("echowhale-tests"))
    return span_exporter
