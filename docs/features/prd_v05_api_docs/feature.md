# PRD 升版 v0.5 与 API 文档（prd_v05_api_docs）

> 审计报告（audit-report-EchoWhale-2026-10-01.md）Schedule Later 第 21 项 +
> Documentation 维度（第 13 节）：PRD 与实现漂移、API 协议层无文档。
> Trellis 任务：`.trellis/tasks/10-03-prd-v05-api-docs`。
> **硬约束：生产代码零改动**——只允许改 `docs/**` 与 `README.md`。

## 目标

1. **PRD v0.5 重写**（docs/prd.md）：审计确认漂移是系统性的——§2.3 非目标写"第一版暂不做语音识别"（Deepgram 实时语音已上线）、§7 写"第一版允许先使用内存存储或 mock 数据"（现实是 PostgreSQL + SQLAlchemy + Alembic + Redis/RQ + mock/live 双运行时）、§10 验收标准缺语音 / 流式 / 档案 / 复盘 / 场景文案下发、§7–§10 内部编号错位。按"重写当前形态而非增量 patch"（design D1）处理。
2. **API 协议层文档**（docs/api.md，design D2 单文件）：统一信封、错误码、限流配额、SSE 事件协议、202 轮询、身份模型、游标分页、请求体上限、X-Request-ID、健康端点。
3. **准确性机制**（design D3）：每个可验证声明写前回读代码核对；本文附"声明 ↔ 代码出处"对照表为验收物。文档腐化比缺文档更糟：不确认的细节标注"以代码为准"。

## 实现说明

### 1. docs/prd.md（v0.5 重写）

按 design 第 3 节映射表逐节执行：

- §1–§2 按"产品现在是什么"重写；§2.1 MVP 目标标注已达成；§2.3 非目标：语音识别移出（语音练习已上线），**发音打分仍在非目标**
- §3 用户流程补 202 异步分析分支、流式输出、语音练习流程、示例场景（后端下发 coffee/office/street）
- §4 功能需求补产品级描述：4.6 流式回复（SSE）、4.7 语音练习、4.8 学员档案（CEFR / 错误画像 / 场景频次，注入教练与反馈提示词）、4.9 LLM 复盘（增强分支，失败降级模板）、4.10 场景文案服务端下发；4.1 补 12MB 请求体门与 202
- §6 目录结构修正漂移（db 层 → PostgreSQL；tasks/ 已承载 RQ 消费；migrations 已是 Alembic 13 版）
- §7 技术方案重写：PostgreSQL + SQLAlchemy + Alembic、Redis + RQ（auth-mail / scene-analysis）、mock/live 双运行时（MODEL_RUNTIME_MODE）、签名访客 Cookie、Deepgram；删除"第一版允许先使用内存存储或 mock 数据"
- §10 验收标准补功能验收（流式 / 语音 / 档案 / 复盘 / 场景文案下发 / 202）与工程验收（门禁数字）
- §11 版本规划：v0.1–v0.4 标注完成态（历史记录口吻），v0.4 后已交付批次集中注记，新增 v0.5 阶段意图（四候选：档案读取 API 与前端进度页、LLM ReviewCopy 生产消费、评测驱动提示词修正、OTel/Langfuse 可观测性），注明"进度记录归 docs/versions/ 与 docs/control 控制面，PRD 不做 changelog"
- 修复 §7–§10 内部编号错位（旧文档把 7.1 写成 6.1、8.1 写成 7.1 等）

### 2. docs/api.md（新文件，十一章节）

design 第 2 节十章节全齐；think 代理的偏离细节（OpenAI 风格错误、模型白名单、SSE 透传）单独成 §11，避免 §1 总览膨胀。写作顺序：先核实后落笔，数值只从 config.py / exceptions.py / 路由文件摘取。

### 3. README.md

"部署"小节之后新增"文档"小节，仅三个链接（PRD / API 参考 / 部署手册），其余章节零改动。

## 声明 ↔ 代码出处对照表（核心验收物）

### T1 端点清单

| 声明（api.md §3） | 出处 |
| --- | --- |
| auth 9 端点（register / login / refresh / me / resend-verification / verify-email / forgot-password / reset-password / logout） | `grep -n "@router" api/routes/v1/auth.py` 实测 9 个（design.md 写 8，以 grep 为准，见"发现"） |
| media 4 端点（upload / get / access-url / scene-analysis） | api/routes/v1/media.py `@router` 4 处 |
| sessions 7 端点（start / get / reply / reply/stream / review / voice/bootstrap / voice/complete） | api/routes/v1/sessions.py `@router` 7 处 |
| history 3 端点 | api/routes/v1/history.py `@router` 3 处 |
| deepgram 1 端点 | api/routes/v1/deepgram.py `@router.post("/think/chat/completions")` |
| 根级 /health、/readyz 不在 /api/v1 前缀下 | api/main.py `@app.get("/health")` / `@app.get("/readyz")`；前缀只挂在 v1_router（`app.include_router(v1_router, prefix=settings.api_prefix)`） |
| sample_scene_id ∈ {coffee, office, street} | api/modules/session_engine/schema.py `SampleSceneId = Literal["coffee", "office", "street"]` |
| 会话创建 media_id / sample_scene_id 二选一 | api/contracts/sessions.py `StartSessionRequest.validate_start_source` |

### T2 统一信封与错误码

| 声明（api.md §4） | 出处 |
| --- | --- |
| 信封 `ApiResponse{code,message,data}`；成功 code=200 / message="Success"、data 恒在；失败 data 仅非 None 时出现 | api/common/responses.py `ApiResponse.success` / `ApiResponse.failed` |
| 1001/400 ValidationError；1001/415 UnsupportedMediaTypeError；1001/413 FileTooLargeError；1001/409 InvalidStateError | api/common/exceptions.py 各类定义（ValidationError 子类共享 code=1001） |
| 1002/401 AuthenticationError；1003/403 PermissionDeniedError；1004/404 NotFoundError | api/common/exceptions.py |
| 1005 簇：基类 500、ConfigurationError 500、StorageError 502、ModelProviderError 502、EmailDeliveryError 503、QueuePublishError 503 | api/common/exceptions.py |
| 1006/429 TooManyRequestsError；1007/422 UnsupportedSceneImageError；1008/503 SceneAnalysisUnavailableError；1302/503 VoiceTokenError | api/common/exceptions.py |
| RequestValidationError → 400/1001，data=pydantic errors 数组 | api/main.py `validation_exception_handler`（body_code=1001，data=exc.errors()） |
| HTTPException → code=HTTP 状态码 | api/main.py `http_exception_handler`（body_code=exc.status_code） |
| 未捕获异常 → 500/1005 "Internal server error" | api/main.py `global_exception_handler` |

### T3 身份与归属

| 声明（api.md §2） | 出处 |
| --- | --- |
| Authorization 可选；给了就必须 `Bearer <token>`，否则 401 | api/common/deps.py `get_optional_authenticated_user`（scheme 校验 + AuthenticationError） |
| 访客 Cookie 名 `echowhale_visitor_id` | api/core/config.py `auth_visitor_cookie_name`；api/common/deps.py `VisitorCookie` alias |
| Cookie 值 `<id>.<hex HMAC-SHA256>`，rpartition 拆分 + 恒时比较验签 | api/core/security.py `sign_value` / `verify_signed_value`（rpartition + compare_digest） |
| 验签失败静默重签、经 Set-Cookie 下发（httponly / secure=AUTH_COOKIE_SECURE / samesite=lax / path=/） | api/common/deps.py `get_resource_owner`（fail-closed 注释）+ `apply_visitor_cookie`（set_cookie 参数） |
| owner 前缀 `user:` / `visitor:` | api/common/ownership.py `USER_OWNER_PREFIX` / `VISITOR_OWNER_PREFIX` |
| 越权一律 404 收敛 | api/modules/session_engine/service.py `_ensure_owner`（raise NotFoundError）；api/routes/v1/media.py `get_media_scene_analysis`（归属校验同语义） |
| history 三端点要求认证用户 | api/routes/v1/history.py 三函数均 `Depends(require_authenticated_user)`；api/common/deps.py `require_authenticated_user` |
| 学员档案只对 user: 前缀建档 / 读档 | api/db/learner_profile_db.py（表注释"本表只写 user: 串"）；api/modules/session_engine/agent.py `_learner_context_for_turn` / `_update_learner_profile_for_turn`（`startswith("user:")` 门控） |

### T4 限流配额（值 ↔ config 键名）

| 动作 | 声明配额 | config.py 键 | 消费点 |
| --- | --- | --- | --- |
| session_start | 10 / 3600s + 匿名 IP 50 / 3600s | `llm_session_start_limit` / `llm_session_start_window_seconds` / `llm_session_start_ip_limit` | api/services/llm_rate_limit.py `default_llm_rate_limit_rule`；api/routes/v1/sessions.py `start_session` |
| reply（含 stream） | 30 / 3600s + IP 150 / 3600s | `llm_reply_limit` / `llm_reply_window_seconds` / `llm_reply_ip_limit` | 同上；sessions.py `reply_to_session` 与 `stream_reply_to_session` 共用 `action="reply"` |
| media_upload | 20 / 3600s + IP 100 / 3600s | `media_upload_limit` / `media_upload_ip_limit`；窗口常量 `MEDIA_UPLOAD_WINDOW_SECONDS=3600` | llm_rate_limit.py；media.py `upload_media` |
| voice_bootstrap | 5 / 3600s + IP 25 / 3600s | `voice_bootstrap_limit` / `voice_bootstrap_ip_limit`；`VOICE_BOOTSTRAP_WINDOW_SECONDS=3600` | llm_rate_limit.py；sessions.py `bootstrap_voice_session` |
| think_proxy | 120 / 300s（per-sid） | `think_proxy_limit` / `think_proxy_window_seconds` | llm_rate_limit.py（key=session_id）；deepgram.py `rate_limiter.consume(action="think_proxy", key=session_id)` |
| auth 7 action | register 5 / login 8 / refresh 20 / resend_verification 5 / verify_email 10 / forgot_password 5 / reset_password 8，窗口 300s | api/services/auth_rate_limit.py `DEFAULT_AUTH_RATE_LIMITS`（键含邮箱 + IP） | auth_rate_limit.py `AuthRateLimiter.consume` |
| 邮件节流 | 冷却 60s / 日 5 封 / 验证码 5 次 | `auth_email_send_cooldown_seconds` / `auth_email_send_daily_limit` / `auth_email_verify_max_attempts` | api/core/config.py |

限流机制声明：

| 声明 | 出处 |
| --- | --- |
| 未配 REDIS_URL → 进程内滑动窗口 + LRU（1 万键） | llm_rate_limit.py `InMemoryLLMRateLimiter`（OrderedDict + max_keys）；`get_llm_rate_limiter` 工厂；config.py `rate_limiter_max_keys=10_000` |
| 配了 Redis → 固定窗口 INCR + 首次 EXPIRE；Redis 故障降级进程内 | llm_rate_limit.py `RedisLLMRateLimiter.consume`（RedisError → fallback）；auth_rate_limit.py `RedisAuthRateLimiter` 同构 |
| IP 键只取 TCP 对端（request.client.host），不取 XFF | llm_rate_limit.py `consume_with_ip_guard`（docstring 与实现 `f"ip:{request.client.host}"`） |
| 认证用户不吃 IP 键；owner 键先耗、IP 键后耗 | llm_rate_limit.py `consume_with_ip_guard`（`if not owner.is_anonymous: return`） |
| 429 → 信封 code 1006；LLM 路径文案"请求过于频繁，请稍后再试。" | exceptions.py `TooManyRequestsError`（code=1006）；llm_rate_limit.py `RATE_LIMIT_MESSAGE` |
| auth 各 action 独立英文文案 | auth_rate_limit.py `DEFAULT_AUTH_RATE_LIMITS` 每 rule 携带 message |

### T5 SSE 事件协议

| 声明（api.md §6） | 出处 |
| --- | --- |
| `POST /sessions/{id}/reply/stream`，media_type `text/event-stream`，响应头 Cache-Control: no-cache、X-Accel-Buffering: no | api/routes/v1/sessions.py `stream_reply_to_session`（StreamingResponse 参数） |
| 事件序 feedback → delta* → session | api/modules/session_engine/agent.py `stream_reply`（yield 序）；sessions.py `_reply_sse_events`（事件名分派） |
| feedback 载荷 = PracticeFeedbackResponse（grammar / more_natural / useful_words / next_step） | api/contracts/sessions.py `PracticeFeedbackResponse`；sessions.py `data = event_payload.model_dump()` |
| delta 载荷 `{"text": ...}`；session 载荷 = SessionReplyResponse | sessions.py `_reply_sse_events`（delta 分支 `{"text": event_payload}`、session 分支 `from_session().model_dump()`） |
| error 事件 `{code,message,data}` 与信封同构；EchoWhaleError → exc.code；意外异常 → 1005 | sessions.py `_reply_sse_events` except 分支 |
| 开流前错误走统一信封 + HTTP 状态 | sessions.py `stream_reply_to_session` docstring（"鉴权/限流/404 等前置校验全部发生在开流之前"） |
| 客户端断连 CancelledError 重抛，失败轮次不落库 | sessions.py `except asyncio.CancelledError: raise`；agent.py `stream_reply`（落库在全部 delta 之后） |
| 与普通 reply 共用 reply 配额 | sessions.py `stream_reply_to_session` 中 `consume_with_ip_guard(action="reply", ...)` |

### T6 202 场景分析轮询

| 声明（api.md §7） | 出处 |
| --- | --- |
| 202 + `{status:"analyzing", media_id}` | api/routes/v1/sessions.py `start_session`（isinstance SceneAnalysisPending → HTTP_202_ACCEPTED）；api/contracts/sessions.py `SessionStartPendingResponse`（Literal["analyzing"]） |
| 触发条件：缓存未命中 + `SCENE_ANALYSIS_ASYNC_ENABLED=true` | api/core/config.py `scene_analysis_async_enabled`；api/modules/session_engine/agent.py `_dispatch_scene_analysis`（live 模式 + 开关 + 入队返回 True 才挂起） |
| 轮询端点：无快照 status="unknown"；有快照含 status / prompt_version / scene / role / confidence / error_code | api/routes/v1/media.py `get_media_scene_analysis`；api/contracts/media.py `SceneAnalysisStatusResponse` |
| 就绪后重试 start，缓存命中 → 200 会话 | agent.py `start`（`_load_cached_scene_analysis` 命中直接建会话；prompt_version 不一致放弃命中） |

### T7 游标分页

| 声明（api.md §8） | 出处 |
| --- | --- |
| limit 1–100 默认 20 | api/routes/v1/history.py `Query(default=20, ge=1, le=100)`（两处） |
| 响应 `page={has_more, next_cursor}` | api/contracts/history.py `CursorPageResponse`（经 HistoryListResponse / HistoryReplayPageResponse 下发） |
| 会话列表游标 `{ISO8601}\|{session_id}\|{hex hmac}`，HMAC-SHA256、密钥 AUTH_JWT_SECRET | api/modules/session_engine/agent.py `_encode_history_cursor` / `_sign_cursor_payload` |
| 游标篡改 / 非法 → 400 / 1001 | agent.py `_decode_history_cursor`（raise ValidationError，即 AppValidationError） |
| 会话列表 keyset `(updated_at, id)` 倒序 | api/db/session_db.py `list_user_sessions_page`（`updated_at < cursor_time OR (== AND id < cursor_id)`，order_by desc） |
| 消息回放游标 = 裸 message id；非法 → 404 / 1004 | session_db.py `list_session_messages_page`（cursor 作 MessageRecord.id 查 position，None → NotFoundError） |
| 消息回放按 position 倒序取页、页内正序返回 | session_db.py `list_session_messages_page`（order_by position.desc().limit(limit+1)，`page = list(reversed(page_desc))`） |

### T8 请求体上限与 X-Request-ID

| 声明（api.md §9） | 出处 |
| --- | --- |
| 全局 12MB | api/core/config.py `max_request_body_bytes = 12 * 1024 * 1024`（注释：10MB 媒体 + multipart 余量） |
| Content-Length 超限不读 body 直接 413 信封（code 1001，"Request body too large"） | api/common/middleware.py `BodySizeLimitMiddleware.__call__` + `_send_rejection`（body_code=FileTooLargeError.code） |
| chunked 逐块计数超限先发 413 再断 | middleware.py `_guard_streaming_body`（tracking_receive 计数，response_started 未开始才发 413） |
| 413 响应不带 X-Request-ID | api/main.py 挂载顺序注释（request-id 内层、body 门外层 → 拒绝发生在上下文建立前）；中间件顺序 `add_middleware(RequestContextMiddleware)` 先于 `add_middleware(BodySizeLimitMiddleware)` |
| X-Request-ID 合法（非空、≤64、ASCII 可打印）则复用，否则 `req_<16hex>` | api/common/request_context.py `is_reusable_request_id` / `generate_request_id` / `ensure_request_id`（MAX_INBOUND_REQUEST_ID_LENGTH=64） |
| 响应头恒回写；日志经 RequestIdFilter 携带 | middleware.py `RequestContextMiddleware.send_with_request_id`；request_context.py `RequestIdFilter` / `configure_request_id_logging` |

### T9 /health 与 /readyz

| 声明（api.md §10） | 出处 |
| --- | --- |
| /health liveness 恒 200 `{"status":"ok"}`，纯 dict 不走信封 | api/main.py `healthcheck`（返回 dict，非 ApiResponse） |
| /readyz 实时探测无缓存；db=SELECT 1 → up/down | main.py `probe_database`（`text("SELECT 1")`，异常归一为 down） |
| redis：配置了才 PING；未配置 "unconfigured" | main.py `probe_redis`（`settings.redis_url` 为空 → "unconfigured"；socket 超时写死 2s） |
| r2：仅查配置齐备性 configured/missing，零网络 | main.py `probe_r2_config`（三凭证 all()，docstring 说明不做真实探测） |
| 仅 db 或 redis=down 时 503 `{"status":"unready","checks":{...}}` | main.py `readyz`（`unready = db down or redis down`；unconfigured/missing 不参与） |

### T10 Think 代理特例

| 声明（api.md §11） | 出处 |
| --- | --- |
| 错误为 OpenAI 风格 `{error:{message,type}}`，不走信封 | api/routes/v1/deepgram.py `_error_response` |
| 401 authentication_error / 400 invalid_request_error / 429 rate_limit_error / 500 configuration_error / 502 upstream_error、upstream_invalid_response | deepgram.py 各 return `_error_response(...)` 分支 |
| Bearer 为受限签名令牌（含 sid）；sid 不存在统一 401 | deepgram.py `DeepgramThinkProxyTokenCodec().decode` + `_extract_session_id(claims)`；`get_session_head` NotFoundError → 401（不泄露存在性注释） |
| model 白名单 = `DEEPGRAM_AGENT_THINK_MODEL` | deepgram.py `_validate_proxy_payload`（`allowed_model = settings.deepgram_agent_think_model`）；生产门控强制非空（config.py `validate_runtime`） |
| SSE 流式透传 | deepgram.py `_stream_think_response` / `_iter_sse_bytes`（content-type text/event-stream 透传） |
| per-sid 限流 120/300s | deepgram.py `rate_limiter.consume(action="think_proxy", key=session_id)`；T4 同源 |

## 验证

- 写作机制：每节落笔前回读对应代码文件（清单见各 T 表"出处"列）；数值只摘自 config.py / exceptions.py / auth_rate_limit.py / contracts，未凭记忆写任何数字。
- 自检 grep：docs/prd.md 不得再出现"第一版暂不做""内存存储或 mock 数据""第一版允许"（本批交付后 grep 零命中，见 progress 文档记录）。
- 门禁（纯文档批次，全绿即证明零代码改动）：`uv run pytest tests --cov=api`（基线 540 passed / 9 skipped，fail_under=87）、`uv run ruff check api tests tools`、`uv run black --check api tests tools`、`cd frontend && npm run typecheck && npm run coverage`（四阈值 76/74/78/76）；`git diff --stat` 仅 docs/** 与 README.md。
- 审查门：从对照表随机抽 5 条声明按出处回读代码复核（抽查结果记入 progress 文档）。

## 发现（核对中清单与代码不一致处）

1. **auth 端点数**：任务 design.md §2 与派发清单初稿写"auth 8"，`grep @router` 实测 **9**（register / login / refresh / me / resend-verification / verify-email / forgot-password / reset-password / logout）——README 既有"API 概览"表也少列 resend-verification。按派发指示"以 grep 为准"写 9；README 该表已由主会话在本批补上 resend-verification 行（README 属本批允许改动范围）。
2. **think 代理模型白名单的空值语义**：`_validate_proxy_payload` 在 `DEEPGRAM_AGENT_THINK_MODEL` 为空时跳过白名单校验（`if allowed_model and ...`）；因生产门控强制该值非空，实际不构成暴露面。api.md 按此精确表述并注明生产门控。
3. 其余清单条目（信封 / 错误码 / 限流 / SSE / 202 / 游标 / 身份 / 上限 / 健康端点）与代码逐条一致，未发现其他不符。

## 遗留

- 控制面登记与 agent_ops render/check（implement.md 第 6 步）由主会话在提交前执行，本子代理未动 docs/control/。
- docs/api.md 与 Swagger 的 schema 细节可能随代码演进漂移；各节已附代码路径，后续改协议时按"先改代码、同步 api.md、更新对照表"的顺序维护。
- PRD §11 v0.5 四候选为意图列表，不含时间表；逐项立项时再补任务工件。
