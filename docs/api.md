# EchoWhale API 参考

> 对外协议层文档：统一信封、错误码、限流、SSE、202 轮询、身份模型、游标分页、
> 请求体上限、健康端点。schema 级细节以 Swagger（应用运行时的 `/docs`）为准，
> 本文与其冲突时**以代码为准**（各节附代码出处）。

## 1. 总览

- Base URL：所有业务接口前缀 `/api/v1`（`API_PREFIX`，见 [config.py](../api/core/config.py)）
- Swagger UI：`/docs`（FastAPI 默认，覆盖请求 / 响应 schema，不覆盖本文的协议层语义）
- **不走统一信封的端点**：
  - `GET /health`、`GET /readyz`（轻量 JSON，消费方是基础设施探针，见 §10）
  - `POST /api/v1/deepgram/think/chat/completions`（OpenAI 风格错误，消费方是 Deepgram Agent，见 §11）

## 2. 认证与身份

身份是“可选 Bearer + 匿名访客 Cookie”双轨（实现：[deps.py](../api/common/deps.py)、[ownership.py](../api/common/ownership.py)）：

| 场景 | 行为 |
| --- | --- |
| 不带 `Authorization` | 匿名访客；依赖访客 Cookie 建立身份 |
| 带 `Authorization: Bearer <token>` | 认证用户；token 非法 → 401 / 1002 |
| 带了但不是 `Bearer` 前缀 | 401 / 1002（给了就必须合法，不静默降级为匿名） |

**签名访客 Cookie**：

- 名 `echowhale_visitor_id`（`AUTH_VISITOR_COOKIE_NAME`）；值为 `<visitor_id>.<hex HMAC-SHA256>`，由服务端用 `AUTH_JWT_SECRET` 签发（[security.py](../api/core/security.py) `sign_value` / `verify_signed_value`，`rpartition` 拆分 + 恒时比较）
- 验签失败（伪造 / 畸形 / 旧版未签名）不报错：静默视为“无访客身份”，重新签发并经 `Set-Cookie` 下发（`httponly`、`secure=AUTH_COOKIE_SECURE`、`samesite=lax`、`path=/`）
- 客户端无法构造出能通过验签的自选 visitor_id

**资源归属（owner 串）**：认证用户 `user:<users.id>`，访客 `visitor:<visitor_id>`；该串贯穿存储路径、限流键与学员档案门控。

**越权语义**：访问不属于自己的资源（会话 / 媒体）一律返回 404 / 1004，不区分“不存在”与“无权”（防存在性探测，[service.py](../api/modules/session_engine/service.py) `_ensure_owner`）。

**端点级差异**：

- history 三端点要求认证用户（`require_authenticated_user`），访客不可用
- 学员档案只对 `user:` 前缀建档 / 读档，visitor 会话零档案读写（[learner_profile_db.py](../api/db/learner_profile_db.py)、[agent.py](../api/modules/session_engine/agent.py) 前缀门控）

## 3. 端点清单

| 资源 | 方法 | 路径 | 说明 |
| --- | --- | --- | --- |
| Auth | POST | `/api/v1/auth/register` | 注册（发验证邮件） |
| | POST | `/api/v1/auth/login` | 登录 |
| | POST | `/api/v1/auth/refresh` | 刷新令牌 |
| | GET | `/api/v1/auth/me` | 当前用户 |
| | POST | `/api/v1/auth/resend-verification` | 重发验证邮件 |
| | POST | `/api/v1/auth/verify-email` | 邮箱验证 |
| | POST | `/api/v1/auth/forgot-password` | 忘记密码 |
| | POST | `/api/v1/auth/reset-password` | 重置密码 |
| | POST | `/api/v1/auth/logout` | 登出 |
| Media | POST | `/api/v1/media/upload` | 上传图片（multipart，≤10MB） |
| | GET | `/api/v1/media/{media_id}` | 媒体元数据 |
| | GET | `/api/v1/media/{media_id}/access-url` | 签名读 URL |
| | GET | `/api/v1/media/{media_id}/scene-analysis` | 场景分析状态（202 轮询用，§7） |
| Sessions | POST | `/api/v1/sessions` | 创建会话（`media_id` 或 `sample_scene_id` 二选一；可能 202，§7） |
| | GET | `/api/v1/sessions/{session_id}` | 会话最新状态 |
| | POST | `/api/v1/sessions/{session_id}/reply` | 回复（整包） |
| | POST | `/api/v1/sessions/{session_id}/reply/stream` | 回复（SSE 流式，§6） |
| | GET | `/api/v1/sessions/{session_id}/review` | 会话复盘 |
| | POST | `/api/v1/sessions/{session_id}/voice/bootstrap` | 语音会话引导（签发 Deepgram 令牌） |
| | POST | `/api/v1/sessions/{session_id}/voice/complete` | 语音会话收口 |
| History | GET | `/api/v1/history/sessions` | 会话列表（认证用户，游标分页 §8） |
| | GET | `/api/v1/history/sessions/{session_id}` | 会话详情（含复盘与消息总数） |
| | GET | `/api/v1/history/sessions/{session_id}/messages` | 消息回放（游标分页 §8） |
| Deepgram | POST | `/api/v1/deepgram/think/chat/completions` | Think 模型代理（§11，非信封） |
| 根级 | GET | `/health` | liveness（§10，非信封） |
| | GET | `/readyz` | readiness（§10，非信封） |

示例场景枚举：`sample_scene_id ∈ {coffee, office, street}`（[schema.py](../api/modules/session_engine/schema.py) `SampleSceneId`）。

## 4. 统一信封与错误码

所有业务接口返回信封 `ApiResponse{code, message, data}`（[responses.py](../api/common/responses.py)）：

- 成功：`code=200`、`message="Success"`，`data` 恒在（可为 null）
- 失败：`data` 仅在非 None 时出现（缺省即省略字段）

错误码 ↔ HTTP 状态 ↔ 异常类（[exceptions.py](../api/common/exceptions.py)）：

| code | HTTP | 异常类 / 来源 | 说明 |
| --- | --- | --- | --- |
| 1001 | 400 | `ValidationError` | 入参非法 |
| 1001 | 415 | `UnsupportedMediaTypeError` | 媒体类型不支持（同码不同状态） |
| 1001 | 413 | `FileTooLargeError` | 文件超限（含请求体门 413，§9） |
| 1001 | 409 | `InvalidStateError` | 状态冲突（如媒体未上传完成） |
| 1002 | 401 | `AuthenticationError` | 未认证 / token 非法 |
| 1003 | 403 | `PermissionDeniedError` | 已认证但无权限 |
| 1004 | 404 | `NotFoundError` | 资源不存在（含越权收敛，§2） |
| 1005 | 500 / 502 / 503 | `EchoWhaleError` 基类、`ConfigurationError`(500)、`StorageError`(502)、`ModelProviderError`(502)、`EmailDeliveryError`(503)、`QueuePublishError`(503) | 应用 / 配置 / 存储 / 模型供应商 / 邮件 / 队列错误 |
| 1006 | 429 | `TooManyRequestsError` | 限流（§5） |
| 1007 | 422 | `UnsupportedSceneImageError` | 非场景图片 |
| 1008 | 503 | `SceneAnalysisUnavailableError` | 图片分析暂时不可用 |
| 1302 | 503 | `VoiceTokenError` | Deepgram 令牌签发失败 |

三个特殊映射（[main.py](../api/main.py) 异常处理器）：

| 来源 | 响应 |
| --- | --- |
| pydantic 请求校验失败（`RequestValidationError`） | 400 / 1001，`data` = pydantic errors 数组 |
| 框架 `HTTPException` | 信封，`code` = HTTP 状态码本身 |
| 未捕获异常 | 500 / 1005，`message="Internal server error"` |

## 5. 限流

两个限流器同一形态：未配 `REDIS_URL` 用进程内滑动窗口 + LRU（1 万键上限，`RATE_LIMITER_MAX_KEYS`）；配了用 Redis 固定窗口（INCR + 首次 EXPIRE）；Redis 故障自动降级进程内。实现：[llm_rate_limit.py](../api/services/llm_rate_limit.py)、[auth_rate_limit.py](../api/services/auth_rate_limit.py)。

**LLM / 会话路径配额**（值 ↔ [config.py](../api/core/config.py) 键名）：

| 动作 | owner 键配额 | 匿名 IP 伴生键配额 | config 键 |
| --- | --- | --- | --- |
| 创建会话 | 10 / 3600s | 50 / 3600s | `LLM_SESSION_START_LIMIT(_IP_LIMIT)` |
| 回复（含 stream） | 30 / 3600s | 150 / 3600s | `LLM_REPLY_LIMIT(_IP_LIMIT)` |
| 媒体上传 | 20 / 3600s | 100 / 3600s | `MEDIA_UPLOAD_LIMIT(_IP_LIMIT)` |
| 语音 bootstrap | 5 / 3600s | 25 / 3600s | `VOICE_BOOTSTRAP_LIMIT(_IP_LIMIT)` |
| Think 代理 | 120 / 300s（按令牌内 sid） | 无 | `THINK_PROXY_LIMIT(_WINDOW_SECONDS)` |

**Auth 路径配额**（300s 窗口，键含邮箱 + IP，每 action 独立英文超限文案）：

| action | 配额 |
| --- | --- |
| register | 5 |
| login | 8 |
| refresh | 20 |
| resend_verification | 5 |
| verify_email | 10 |
| forgot_password | 5 |
| reset_password | 8 |

**键语义**（`consume_with_ip_guard`）：

- IP 键只取 TCP 对端地址（`request.client.host`），**不解析** `X-Forwarded-For`（可伪造）；反代后要恢复真实 IP 见 [deployment.md](deployment.md) §6
- IP 伴生键只对匿名访客生效；认证用户只吃 owner 键
- owner 键先消耗、IP 键后消耗，任一超限即 429

**429 形态**：统一信封 `code=1006`。LLM 路径文案固定中文“请求过于频繁，请稍后再试。”；auth 各 action 独立英文文案。

**邮件发送节流**（[config.py](../api/core/config.py)）：同地址冷却 60 秒（`AUTH_EMAIL_SEND_COOLDOWN_SECONDS`）、每日 5 封（`AUTH_EMAIL_SEND_DAILY_LIMIT`）、验证码最多尝试 5 次（`AUTH_EMAIL_VERIFY_MAX_ATTEMPTS`）。

## 6. SSE 事件协议（流式回复）

`POST /api/v1/sessions/{session_id}/reply/stream`，请求体同普通 reply（[sessions.py](../api/routes/v1/sessions.py) `stream_reply_to_session`）。

- 响应：`Content-Type: text/event-stream`，响应头 `Cache-Control: no-cache`、`X-Accel-Buffering: no`
- 事件序（[agent.py](../api/modules/session_engine/agent.py) `stream_reply`）：**`feedback` → `delta*` → `session`**
  - `feedback`：`data` = PracticeFeedbackResponse（`grammar` / `more_natural` / `useful_words` / `next_step`，见 [contracts/sessions.py](../api/contracts/sessions.py)）
  - `delta`：`data` = `{"text": "<增量文本>"}`
  - `session`：`data` = SessionReplyResponse（与整包 reply 的 data 同构）
- 错误形态：`error` 事件，`data` = `{code, message, data}` 与信封同构
  - 开流前错误（401 / 404 / 429 / 请求校验等）**不走 SSE**：仍返回统一信封 + 对应 HTTP 状态码
  - 开流后业务异常（`EchoWhaleError`）：`error` 事件，`code` = 异常自身的业务码
  - 开流后意外异常：`error` 事件，`code=1005`
- 取消语义：客户端断连以 `CancelledError` 重抛，失败轮次不落库（部分 delta 已下发但该轮消息不入库）
- 限流：与普通 reply 共用 `reply` 配额（§5）

## 7. 202 场景分析轮询

创建会话携带 `media_id` 且场景分析缓存未命中、异步开关开启（`SCENE_ANALYSIS_ASYNC_ENABLED=true`）时，协议走“挂起 → 轮询 → 重试”（[sessions.py](../api/routes/v1/sessions.py) `start_session`、[media.py](../api/routes/v1/media.py) `get_media_scene_analysis`）：

1. `POST /api/v1/sessions` → **202**，`data = {status: "analyzing", media_id}`（[contracts/sessions.py](../api/contracts/sessions.py) `SessionStartPendingResponse`）
2. 客户端轮询 `GET /api/v1/media/{media_id}/scene-analysis`，`data` = `SceneAnalysisStatusResponse`：
   - 无快照：`status="unknown"`
   - 有快照：`status` / `prompt_version` / `scene` / `role` / `confidence` / `error_code`（[contracts/media.py](../api/contracts/media.py)）
3. 状态就绪后重试 `POST /api/v1/sessions`（同 `media_id`），缓存命中 → 200 正常会话载荷

## 8. 游标分页

history 列表与消息回放均为游标分页（[history.py](../api/routes/v1/history.py)）：

- `limit`：1–100，默认 20
- 响应 `data.page = {has_more, next_cursor}`；`has_more=false` 时 `next_cursor` 为 null

两种游标（对客户端均应视为 opaque 不透明串）：

| 游标 | 格式 | 篡改 / 非法 |
| --- | --- | --- |
| 会话列表 | `{ISO8601 时间戳}\|{session_id}\|{hex HMAC-SHA256}`，密钥 `AUTH_JWT_SECRET`（[agent.py](../api/modules/session_engine/agent.py) `_encode_history_cursor`） | 400 / 1001 |
| 消息回放 | 裸 message id，无签名（[session_db.py](../api/db/session_db.py)） | 404 / 1004 |

- 会话列表按 `(updated_at, id)` 倒序 keyset 分页
- 消息回放按 `position` 倒序取页、页内按正序返回（回放语义：从最新往旧翻页，单页内消息顺序自然）

## 9. 请求体上限与 X-Request-ID

**全局请求体门**：12MB（`MAX_REQUEST_BODY_BYTES` = 10MB 媒体上限 + multipart 余量；[middleware.py](../api/common/middleware.py) `BodySizeLimitMiddleware`）：

- 头部声明 `Content-Length` 超限：不读 body 直接 413 信封（`code=1001`，`message="Request body too large"`）
- 无 Content-Length（chunked）：逐块计数，超限先发 413 再停止转发
- **边界**：413 响应不带 `X-Request-ID`——拒绝发生在 request-id 上下文建立之前（中间件序见 [main.py](../api/main.py) 注释），属已知盲区

**X-Request-ID**（[request_context.py](../api/common/request_context.py)）：

- 入站合法（非空、≤64 字符、ASCII 可打印）则复用；否则生成 `req_<16hex>`
- 响应头恒回写 `X-Request-ID`（SSE 等流式响应的头在开流前发送，同样生效）
- 服务端日志经 `RequestIdFilter` 携带同一 id，可用于串联一次请求的全部日志

## 10. /health 与 /readyz

| 端点 | 语义 | 响应 |
| --- | --- | --- |
| `GET /health` | liveness：进程活着即 200，不做依赖探针 | `200 {"status":"ok"}` |
| `GET /readyz` | readiness：依赖实测，每次请求实时探测、无缓存 | `200 {"status":"ready","checks":{...}}` 或 `503 {"status":"unready","checks":{...}}` |

`/readyz` 探针项（[main.py](../api/main.py)）：

| 检查项 | 方式 | 取值 |
| --- | --- | --- |
| `db` | `SELECT 1` 实测 | `up` / `down` |
| `redis` | 配置了 `REDIS_URL` 才 `PING` 实测 | `up` / `down` / `unconfigured`（未配置） |
| `r2` | 仅查三项凭证配置齐备性，零网络 | `configured` / `missing` |

**unready 判定**：仅 `db` 或 `redis` 为 `down` 时 503；`unconfigured` / `missing` 是“未部署”而非“坏了”，不影响判定。

两端点均为轻量 JSON，不走统一信封（消费方是 LB / K8s 等基础设施）。

## 11. Think 代理特例（Deepgram）

`POST /api/v1/deepgram/think/chat/completions` 的调用方是 Deepgram Agent（不是前端），协议刻意偏离统一信封（[deepgram.py](../api/routes/v1/deepgram.py)）：

- 认证：`Authorization: Bearer <受限签名令牌>`——语音 bootstrap 签发、内含会话 sid；缺失 / 非法 / 会话不存在 → 401
- **错误格式为 OpenAI 风格 `{error: {message, type}}`，不走统一信封**：

| HTTP | type | 场景 |
| --- | --- | --- |
| 401 | `authentication_error` | 令牌缺失 / 解码失败 / 会话不存在 |
| 400 | `invalid_request_error` | JSON 非法 / payload 校验失败 / 模型不在白名单 |
| 429 | `rate_limit_error` | per-sid 配额超限（§5） |
| 500 | `configuration_error` | 代理上游配置缺失 |
| 502 | `upstream_error` / `upstream_invalid_response` | 上游请求失败 / 返回非 JSON |

- `model` 白名单 = `DEEPGRAM_AGENT_THINK_MODEL`（生产门控强制配置）
- 支持 SSE 流式透传（`stream: true` 时原样转发上游 `text/event-stream`）
