# OTel 可观测性接入：按引擎打 span（otel_engine_spans）

> 审计报告（audit-report-EchoWhale-2026-10-01.md）Schedule Later 第 19 项 +
> 对标结论 7（Dify ObservabilityLayer 插件化追踪）；PRD §11 v0.5 候选④。
> Trellis 任务：`.trellis/tasks/10-03-otel-engine-spans`。

## 目标

为后端接入 OpenTelemetry 链路追踪：一次请求里"场景分析、教练、反馈、复盘"各自的
耗时/成败/token 能在追踪视图里分解，多 provider failover 可归因。默认关闭、零行为、
零厂商锁定；Langfuse 原生消费 OTLP，Jaeger / 任何 OTLP 后端皆可。

## 范围

### In scope

- **三层 span（收口在咽喉点，不撒网）**：
  - server 层：`TracingMiddleware`（`api/common/middleware.py`，纯 ASGI，管线最内层、
    request-id 之内），属性含 request_id / http.method / http.target / http.route
    （路由模板回填）/ http.status_code / `echowhale.terminal`；`/health`、`/readyz` 旁路。
  - engine 层：`session_engine/agent.py` 的 scene / coach / feedback / review 四分支经
    `traced_engine` 包裹，终态三值 `ok / degraded / failed` 与既有 failure policy 逐条对齐。
  - provider attempt 层：`resilience.py::run_llm_with_failover` 每次 attempt（含重试）
    一个 `llm.attempt` span；`openai.py` payload builder stamp `llm.model`、
    `_record_usage` stamp token 三元组。
- **跨层关联**：全 span 携带 `echowhale.request_id`（ContextVar 复用），engine span 尽力携带
  `echowhale.session_id`。
- **配置与依赖**：`opentelemetry-api` / `opentelemetry-sdk` /
  `opentelemetry-exporter-otlp-proto-http`（禁 gRPC 变体）入 pyproject + uv.lock；
  Settings 只增 `otel_enabled: bool = False`，标准 `OTEL_*` 环境变量由 SDK 原生消费。
- **文档**：`docs/observability.md`（新）、`.env.example` OTel 注释段、README 入口。

### Out of scope（遗留项）

- usage owner/session 归因（需 owner ContextVar 贯穿，独立小遗留）。
- 自动插桩库（DB/Redis auto-instrumentation，噪声大于收益）。
- Langfuse 账号/云端配置（用户侧操作，文档给步骤）。
- 前端埋点。
- 异步场景分析 worker（api/tasks/image_analysis.py）内的 span（非编排层咽喉点）。
- 入站 traceparent 传播（W3C 分布式上下文提取）。

## 实现说明（关键决策）

- **模块级 tracer，不动全局 provider**（`api/common/telemetry.py`）：绝不调用
  `trace.set_tracer_provider()`——手动埋点全部经自有 `_tracer` 引用，绕开 OTel
  "provider 只能设一次"约束，测试整体 monkeypatch `_tracer` 零污染隔离。
- **关闭态锁定**：默认不 import SDK，全链路 NonRecordingSpan；`configure_telemetry()`
  幂等、装配失败降级 warning 保持 no-op；`_ResilientSpanExporter` 吞导出失败 +
  限频 warning（单调钟 60s 一条）。
- **终态映射与 failure policy 同源**：scene/coach 异常 = failed；feedback 异常 = degraded；
  review copy=None（含 mock 短路、feedback 已降级、超时取消）= degraded。
  `terminal=failed` 才置 Status ERROR，degraded 保持默认状态（UNSET，OTel 语义即
  成功）由 `record_exception` 事件 + terminal 属性承载失败痕迹。吞异常/降级转换代码一行未改语义
  （`_degraded_feedback_with_log`、`_resolve_feedback`、`_review_copy_for_turn` 的
  warning 口径原样保留），span 只旁路记账。
- **attempt span 重构等价性**：退避 sleep 移出 span 块（backoff 不计入 attempt 耗时）；
  deadline/重试判定逐条等价，既有 12 个 resilience 测试全绿。
- **流式取舍**：教练流式 span 只覆盖"开流"阶段（跨 async generator 的 yield 会把
  中间态泄漏进消费者上下文，明确不做）；流式 usage 在流末帧到达、落在当时活跃
  span（engine/server）——两项取舍均写入 `docs/observability.md` 第 7 节。

## 验收物

- `api/common/telemetry.py`、`api/common/middleware.py::TracingMiddleware`、
  `api/main.py`（装配 + 管线顺序注释）、`api/integrations/llm/{resilience,openai}.py`、
  `api/modules/session_engine/agent.py`、`api/core/config.py`。
- 测试：`tests/common/test_telemetry.py`、`tests/common/test_tracing_middleware.py`、
  `tests/integrations/test_llm_resilience_tracing.py`（httpx MockTransport，零真实网络）、
  `tests/api/test_telemetry_e2e.py`（start → reply / reply-stream 全栈 span 树）。
- 文档：`docs/observability.md`、`.env.example`、README（文档小节 + 环境变量表行）。

## 验证（门禁数字，主会话复核后可更新）

- `MODEL_RUNTIME_MODE=mock uv run pytest tests --cov=api`：**578 passed / 9 skipped，
  覆盖率 88.91%**（门禁 87；基线 540 passed / 9 skipped、88.49%，只升不降达标）。
- `MODEL_RUNTIME_MODE=mock uv run pytest tests -q`：578 passed / 9 skipped（复跑无顺序依赖）。
- `uv run ruff check api tests tools`、`uv run black --check api tests tools`：全绿。
- 前端零改动（主会话已复核）：`npm run typecheck` 通过；`npm run coverage`
  15 文件 107 passed，All files 85.97 / 77.42 / 84.02 / 85.97 对阈值 76/74/78/76
  全部持平达标；`git status` 确认 frontend/ 无任何改动。

## 发现（核对与实现中的记录）

1. **opentelemetry 1.45.0 的 import 路径差异**：OTLP HTTP 导出器模块为
   `opentelemetry.exporter.otlp.proto.http.trace_exporter`（不是旧文档常见的
   `span_exporter`）；`async with tracer.start_as_current_span(...)` 在该版本
   不支持（`_AgnosticContextManager` 仅实现同步协议）——异步路径统一用同步
   `with`（asyncio 下 contextvar 语义等价）。
2. **`Resource.create({})` 的"未设置"信号**：SDK 默认把 `service.name` 落在
   `unknown_service:<进程>` 占位值上，以该占位前缀为"用户未设置"判定，补默认
   `echowhale-api`，不覆盖显式配置。
3. **既有测试与 mock pin 的冲突（非本批引入）**：`tests/core/test_config.py` 的
   `test_live_model_runtime_requires_configured_model_endpoints` 在
   `MODEL_RUNTIME_MODE=mock` 进程级 pin 下会失败（pydantic-settings 里进程环境
   优先于 tmp env file，覆盖了测试要模拟的 live 场景）——已用
   `monkeypatch.delenv("MODEL_RUNTIME_MODE")` 使该测试在 pin 与不 pin 两种跑法下
   都确定性通过；无 pin 基线行为不变（经 stash 对照验证）。
4. **`_ResilientSpanExporter` 同时处理两条失败路径**：OTLP 导出器（1.45.0）把
   HTTP 错误吞成 `SpanExportResult.FAILURE` 返回值而不抛异常；为落实"日志风暴可控"
   的设计意图，对"抛异常"与"返回 FAILURE"两条路径同款限频记账。
5. **mock 模式的 attempt span 分布**：feedback agent 在 mock 下短路（不经历
   failover），mock e2e 的 reply 只有教练分支产生 `llm.attempt` span——属既有
   引擎行为，非埋点缺失。
6. **docs/api.md 复核：零变动**（预期成立）：未改端点/契约/错误码；413 不带
   X-Request-ID 的盲区边界不受影响（body 门仍在 request-id 与 tracing 之外）。

## 遗留

- 控制面登记与 agent_ops render/check 已由主会话完成（本批收口时一并提交）。
- 前端 typecheck + coverage 复跑已由主会话完成（零改动达标）；Docker 镜像构建兼容
  由 CI docker job 实测（本地引擎未运行，不自测）。
- PRD §11 v0.5 其余三候选（档案读取 API 与进度页、ReviewCopy 生产消费、评测驱动
  提示词修正）待立项。
