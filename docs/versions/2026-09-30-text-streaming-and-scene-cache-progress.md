# 2026-09-30 文字 SSE 流式 + 场景分析缓存落地进度

第三批 agent 架构优化（体验升级）完成，`uv run pytest tests` 224 passed / 2 skipped（基线 190 + 新增 34），前端 vitest 85 passed。

## 文字回复 SSE 流式（`text_reply_streaming`）

- 流式底座：`api/integrations/llm/streaming.py`（SSE 分帧解析、跨 chunk 帧重组、`[DONE]` 终止、末帧 usage、非 SSE JSON 整包降级单 delta）；`base.py` 增加 `TextStream` / `StreamingTextCompletionClient` 可选能力协议；`OpenAICompatibleClient.async_open_text_stream` 打开即校验（状态码 + content-type），4xx 读出错误体后抛 `httpx.HTTPStatusError` 交给 failover
- failover 语义定死：`CoachEngineAgent.stream_reply` 只有"打开流"参与重试与主备切换（复用 `LLMAttempt` 泛型 callable）；开流后中途断流向上传播，不再整体重来
- 编排：`SessionEngineAgent.stream_reply` 事件序 `feedback → delta* → session`；feedback 与 coach 并发启动（首帧不被 coach 打开阻塞），任一分支失败整轮失败、不落任何消息，与非流式 `reply()` 的原子性一致；共享的 `_build_reply_turn` 统一两条路径的落库组装，空 coach 文本按模型失败处理
- 端点 `POST /sessions/{id}/reply/stream`：鉴权 / 限流（action=reply）/ 404 / 422 全部在 `StreamingResponse` 之前（错误保持统一信封）；开流后异常收敛为 `error` 事件（信封同构）；旧 JSON 端点原样保留，回归通过
- 前端 service 层：`sessionApi.ts` 的 `submitPracticeTurnStream`（apiFetch 保留 401 刷新语义 + ReadableStream SSE 解析 + `onFeedback`/`onDelta` 回调 + done 帧复用既有映射层）；按既定决策页面暂不接线，等文字路径 UI 改版
- 配置 `LLM_STREAM_INCLUDE_USAGE`（默认 false）：兼容不支持 `stream_options` 的网关

## 场景分析缓存 + RQ 异步化（`scene_analysis_caching`）

- 新表 `scene_analyses`（media 主键 + FK CASCADE；status/prompt_version/scene/role/opener/visual_anchors/vocab_candidates/confidence/error_code），Alembic `20260930_0010`（down_revision=0009），ORM 同步进 `create_all_tables(_async)` 双轨
- `SceneAnalysisStore` 协议 + SqlAlchemy 实现（upsert 单行幂等）；`start()` 三级分流：命中（ready 且版本一致）→ 直接建会话，不签 URL 不下载不调视觉；未命中且 live+异步开 → `save_pending` + RQ 投递 + `SceneAnalysisPending`（路由 202 + `SessionStartPendingResponse`）；其余内联分析并写穿缓存
- Redis/RQ 缺席降级：`enqueue_scene_analysis` 捕获配置/入队错误记 warning 返回 False，调用方降级内联，同时落 failed 行供状态端点追溯（复用 `llm_rate_limit.py` 的降级形状）
- RQ worker：`run_scene_analysis_task` 自建事件循环与引擎，worker 重签 R2 读 URL（不复用请求里的短 TTL 签名）；`UnsupportedSceneImageError` 记 1007 直接失败不重试，其余失败记 1005 后上抛交给 `Retry(max=3)`；worker 队列扩为 `[auth-mail, scene-analysis]`
- 状态端点 `GET /media/{id}/scene-analysis`：unknown/pending/ready/failed，越权与缺失一律 404
- mock 模式直返不排队；内联 mock 分析照常写穿缓存
- 配置四项：`SCENE_ANALYSIS_CACHE_ENABLED`（默认 false）/ `SCENE_ANALYSIS_ASYNC_ENABLED`（默认 false，前端轮询接线后开）/ `SCENE_ANALYSIS_PROMPT_VERSION`（bump 即整体失效）/ `SCENE_ANALYSIS_QUEUE_NAME`

## 顺手项

- `bootstrap_voice_session` 里的 `voice_token_issuer.issue_token`（同步 SDK 调用）改 `asyncio.to_thread`，不再卡事件循环

## 过程要点（镜像名风险实锤）

- 本批多处工具输出存在字段镜像混淆（`save_reply_turn`/`learner_message`/`vocab_candidates` 等在 grep/渲染层被改写）。全部存量文件修改改用「python 脚本 + count 断言」字节级替换，标识符以 `inspect`/`model_fields` 内省为准；自建的 `stream_reply` 曾把 `aclose()` 写成 `close()`，被直测当场抓住修正——仓储/引擎级直测再次证明是 fake 盲区的必要补偿
- `POST /sessions` 现按缓存分流可能返回 202 挂起载荷，`start_session` 返回类型扩为 `Session | SceneAnalysisPending`；现有前端在异步开关关闭时不受影响

## 留守事项

- 前端轮询 / TextComposer 接线（文字路径 UI 改版批次）
- 生产开启 `SCENE_ANALYSIS_*` 前需确认 worker 消费 scene-analysis 队列
