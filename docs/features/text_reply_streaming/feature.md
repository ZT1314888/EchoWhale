# Feature: `text_reply_streaming`

## 基本信息

- `feature`: `text_reply_streaming`
- `status`: `feature_test_passed`
- `module`: `session_orchestration`
- `cross_module`: `yes`（platform_foundation 的 LLM 流式底座、frontend_app 的 service 层封装）
- `owner`: `lucky`
- `updated_at`: `2026-09-30`
- `merge_target`: `module/session_orchestration`

## 背景

`POST /sessions/{id}/reply` 是阻塞 JSON：首字延迟等于完整生成时间（feedback + coach 两段模型调用全部结束后才返回）。对学习者来说，每轮提交后要盯着空白等好几秒，体验明显落后于语音链路的实时感。

## 用户故事

- 当我发出一条文字练习消息，我希望先立刻看到结构化反馈卡片，再看着教练回复逐字出现，这样我不用干等整段生成。
- 当生成中途失败或网络断流，我希望拿到结构化的错误事件而不是一个空洞的 500，这样前端能给出和 JSON 路径一致的提示。

## 范围

### In scope

- `OpenAICompatibleClient` 新增 `async_open_text_stream`：`stream=true` 的 SSE 分帧解析（跨 chunk 帧重组、`[DONE]` 终止、末帧 usage 计量、非 SSE JSON 整包降级为单 delta）
- `api/integrations/llm/streaming.py`：`HttpxTextStream` / `SingleDeltaTextStream` / `WordChunkedTextStream` 三个流适配器与 SSE 帧解析工具
- `base.py` 新增 `TextStream` / `StreamingTextCompletionClient` 可选能力协议
- coach 引擎：`ChatProvider.open_reply_stream` 可选流式入口 + `CoachEngineAgent.stream_reply`（failover 语义：只有"打开流"参与重试与主备切换，开流后中途断流不再整体重来）
- session 编排：`SessionEngineAgent.stream_reply` 异步生成器，事件序 `("feedback", FeedbackResult)` → `("delta", str)*` → `("session", Session)`；feedback 与 coach 并发启动，先回执 feedback，任一分支失败整轮失败、不落任何消息（与非流式 reply 的原子性一致）
- 路由 `POST /sessions/{id}/reply/stream`（SSE）：鉴权 / 限流 / 404 / 422 全部发生在开流之前（错误仍走统一信封）；开流后异常收敛为 `error` 事件（信封同构，无 HTTP 状态码可改）
- 前端 service 层：`sessionApi.ts` 的 `submitPracticeTurnStream`（fetch ReadableStream + SSE 帧解析，回调 `onFeedback` / `onDelta`，`done` 帧复用既有映射层），PracticeSessionPage 暂不接线（文字路径定位为补充入口，页面接线留待下一批 UI 改版）

### Out of scope

- 语音链路的流式化（Deepgram WebSocket 已是实时通道）
- 语音路径复用 SSE 流式
- PracticeSessionPage 的 TextComposer UI

## 契约

SSE 事件（`text/event-stream`）：

| 事件 | data 载荷 | 语义 |
| --- | --- | --- |
| `feedback` | `FeedbackResult` dump | 本轮三件套反馈，先于正文下发 |
| `delta` | `{"text": "<增量>"}` | 教练回复增量，按序拼接 |
| `session` | `SessionReplyResponse` dump | 全部落库后的完整会话 + feedback（复用 JSON 端点契约） |
| `error` | `{"code", "message", "data"}` | 开流后失败的统一信封同构载荷 |

## 配置

- `LLM_STREAM_INCLUDE_USAGE`（默认 false）：部分 OpenAI 兼容网关不接受 `stream_options.include_usage`，故默认关闭；开启后流式末帧 usage 与整包路径共用 `_record_usage` 落点

## 测试

- `tests/integrations/test_llm_streaming.py`：SSE 解析、跨 chunk 帧重组、usage 末帧计量、非 SSE 降级、开流失败（failover 入口）、`stream_options` 门控
- `tests/modules/test_coach_stream.py`：mock 词片流、真 provider 流（MockTransport）、主备 failover、reply-only provider 单 delta 退化、全失败聚合
- `tests/modules/test_session_stream.py`：事件序、feedback 失败不落库、coach 打开失败取消对侧、中途断流不落库、空回复拒绝
- `tests/api/test_reply_stream_routes.py`：SSE 帧序、业务错误收敛为 error 事件、404/422/429 保持 JSON 信封、旧 JSON 端点回归
- `tests/integration/test_mock_smoke.py`：真实 HTTP 全链路（aiosqlite + mock 引擎）中 SSE 与落库一致性
- `frontend/src/services/sessionApi.test.ts`：SSE 消费、错误事件、开流前信封错误、提前断流
