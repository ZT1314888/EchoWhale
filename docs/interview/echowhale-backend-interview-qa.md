# EchoWhale Python 后端面试题与答案

本文用于准备 EchoWhale Python 后端面试。默认目标岗位是 Python 后端开发，级别按初中级到中级偏上准备。

## 使用方式

- 先背每题的“结论”，保证 30 秒内能回答。
- 面试官追问时，再展开“代码依据”和“权衡”。
- 如果被问到生产化，优先回答“生产级改进”，不要把当前 integrating 状态说成已经 releasable。
- 回答时尽量串到具体文件，例如 `api/main.py`、`api/core/config.py`、`api/modules/session_engine/agent.py`、`api/db/session_db.py`。

## 答题模板

每题按四层回答：

1. **结论**：先直接回答设计是什么。
2. **代码依据**：指出项目中哪里体现了这个设计。
3. **权衡**：说明为什么这样做，以及代价。
4. **生产级改进**：说明如果上线或扩大规模，还要补什么。

---

## 1. 项目总览与架构

### 1.1 你用 2 分钟讲 EchoWhale，怎么让面试官相信它不是 CRUD demo？

**结论**：EchoWhale 不是简单 CRUD，而是一条“图片上传 -> 场景理解 -> 角色化英语对话 -> 逐轮反馈 -> 历史复盘”的 AI 练习链路。它的核心难点在会话编排、模型 provider 抽象、异步并发、对象存储签名 URL、认证身份边界和持久化一致性。

**代码依据**：入口在 `api/main.py`，业务路由在 `api/routes/v1/`；会话主链路由 `api/modules/session_engine/agent.py` 串联 `scene_engine`、`coach_engine`、`feedback_engine`；会话、消息、review 的事务落库在 `api/db/session_db.py`。

**权衡**：CRUD 系统通常围绕单表资源增删改查，EchoWhale 的主要价值在跨模块编排和外部 AI/存储/语音能力的接入。代价是链路更长，失败点更多，需要明确错误边界、回退策略和测试分层。

**生产级改进**：要补系统级 smoke、真实 R2/Redis/SMTP/Deepgram/LLM 联调、全链路 tracing、模型质量评估集和成本监控。当前 `docs/control/project-index.md` 标记系统为 `integrating`，不能说已经完全发布就绪。

### 1.2 为什么拆成 routes -> services -> modules -> db/integrations，而不是把逻辑都放 route？

**结论**：route 只负责 HTTP 入参、依赖注入和响应封装；service 处理应用层编排和权限；modules 处理 AI engine 领域逻辑；db/integrations 隔离数据库和外部服务。这样能让 API、业务编排、模型逻辑和基础设施各自可测试、可替换。

**代码依据**：`api/routes/v1/sessions.py` 只调用 `SessionEngineService`；`api/modules/session_engine/agent.py` 负责调度各 engine；`api/db/session_db.py` 负责事务和 ORM；`api/integrations/storage/r2.py` 封装 R2。

**权衡**：分层会增加文件数量和跳转成本，但能避免 route 变成“上帝函数”。对于 AI 项目尤其重要，因为 prompt、provider、存储和 HTTP contract 的变化频率不同。

**生产级改进**：继续收紧每层职责，例如 route 不直接知道 provider 细节，service 不拼 SQL，engine 不处理 cookie。再配合 contract test 保证层间接口稳定。

### 1.3 scene_engine / coach_engine / feedback_engine / session_engine 的边界分别是什么？

**结论**：`scene_engine` 负责“看图得到可练习场景”；`coach_engine` 负责“按角色接话和追问”；`feedback_engine` 负责“给学习反馈”；`session_engine` 负责“把三者串成会话流程并持久化”。

**代码依据**：模块目录分别位于 `api/modules/scene_engine/`、`api/modules/coach_engine/`、`api/modules/feedback_engine/`、`api/modules/session_engine/`。`SessionEngineAgent.start()` 调 scene engine，`reply()` 并发调 coach 和 feedback。

**权衡**：拆 engine 后可以独立替换模型、prompt 和 schema；代价是 session 层必须承担上下文传递和错误归一化。

**生产级改进**：为每个 engine 建立独立评估集、超时预算、质量指标和 provider fallback 监控，避免一个 engine 的波动拖垮整条会话链路。

### 1.4 如果新增“发音评分 engine”，你放在哪一层，如何接入现有链路？

**结论**：新增 `api/modules/pronunciation_engine/`，属于 modules 层；由 `session_engine` 在语音 complete 或每轮语音结束后调用，再把评分结果写入 review 或单独的 pronunciation record。

**代码依据**：当前语音链路在 `api/modules/session_engine/agent.py` 的 `bootstrap_voice_session()` 和 `complete_voice_session()`；Deepgram 配置在 `api/integrations/deepgram/voice_agent.py`；会话 runtime 事件和 voice fact 在 `api/db/session_db.py`。

**权衡**：放 modules 层能保持“发音评分”作为独立 AI 能力，不污染 route。接入 session_engine 能复用会话上下文和持久化事务，但要注意不要让语音评分阻塞文本主链路。

**生产级改进**：评分结果应有 schema、置信度、音频片段引用、失败降级策略和异步队列。对延迟敏感时，先返回会话结果，再异步补评分。

### 1.5 现在系统状态为什么是 integrating，离 releasable 还差什么？

**结论**：因为多个后端模块已经成型，但真实外部服务和完整系统级联调还没完全收口，所以是 `integrating`。离 `releasable` 还差完整主链路 smoke、真实 provider/R2/Redis/SMTP/Deepgram 验证、部署配置和失败恢复验证。

**代码依据**：`docs/control/project-index.md` 标记 `system: integrating`，并写明主要阻塞包括真实 Redis/SMTP smoke、Deepgram 联调和系统级样本验证。

**权衡**：`integrating` 说明代码结构和模块链路正在汇总，不等于不可用；但 `releasable` 要求可演示、可部署、可回归验证。

**生产级改进**：补 CI、环境变量模板、健康检查、数据库迁移检查、外部依赖 smoke、异常告警和发布回滚说明。

---

## 2. FastAPI 与 API 设计

### 2.1 `api/main.py` 里为什么统一 exception handler？业务错误和 HTTPException 怎么映射？

**结论**：统一 exception handler 是为了让所有错误都落到一致的响应结构，避免 route 各自返回不同格式。业务错误用 `EchoWhaleError` 的 `code/status_code/message/data` 映射；FastAPI 的 `HTTPException` 用 HTTP status 作为业务 code。

**代码依据**：`api/main.py` 注册了 `EchoWhaleError`、`HTTPException`、`RequestValidationError` 和兜底 `Exception` handler，统一调用 `ApiResponse.failed()`。

**权衡**：统一错误格式方便前端处理 toast、登录态和表单错误；代价是要维护业务 code 体系，不能滥用 500。

**生产级改进**：增加 request id、错误分类、结构化日志、敏感信息脱敏和告警级别，避免把内部异常细节暴露给用户。

### 2.2 为什么响应体有 code/message/data，HTTP status 和业务 code 如何分工？

**结论**：HTTP status 表示传输和协议层结果，业务 code 表示应用语义。比如参数错误可以 HTTP 400，同时 body code 是更细的业务错误码；成功时统一返回 `code/message/data`，便于前端稳定消费。

**代码依据**：`api/common/responses.py` 定义统一响应；`api/main.py` 的错误 handler 把 `body_code` 和 `http_code` 分开传入。

**权衡**：这种格式对前端友好，也方便跨端统一；代价是需要团队约定不要只看 HTTP 200，也不要让业务 code 和 HTTP status 冲突。

**生产级改进**：建立错误码文档，明确哪些错误可重试、哪些要重新登录、哪些要展示给用户。

### 2.3 `Depends(get_session_service)` 每次创建 service，有什么性能和生命周期问题？

**结论**：当前每次请求都会构造 `SessionEngineService` 及其依赖对象，优点是无共享状态、便于测试替换；问题是如果构造对象里包含昂贵客户端，就会增加开销。

**代码依据**：`api/routes/v1/sessions.py` 的 `get_session_service()` 每次创建 repository、R2 service 和 session service。

**权衡**：轻量对象每请求创建可以接受，能避免跨请求状态污染；但外部客户端、连接池应缓存或由底层 factory 管理。当前数据库 engine/session factory 在 `api/db/database.py` 用 `lru_cache` 缓存。

**生产级改进**：把昂贵客户端放到 app lifespan 或缓存 factory 中，给 provider client、R2 client、Redis client 设置明确生命周期和关闭逻辑。

### 2.4 哪些 route 应该是 async def，哪些可以是普通 def？

**结论**：会等待 async DB、对象存储、LLM、Deepgram 或读取上传文件的 route 应该用 `async def`；纯同步认证、密码校验、同步 repository 调用可以用普通 `def`。

**代码依据**：`api/routes/v1/sessions.py`、`media.py` 使用 `async def`；`api/routes/v1/auth.py` 多数认证接口是 `def`，因为当前 auth repository 是同步 SQLAlchemy session。

**权衡**：`async def` 适合 IO 并发，但不能在里面直接跑阻塞 SDK；R2 在 `api/integrations/storage/r2.py` 用 `run_in_threadpool` 包装同步 boto3 调用。

**生产级改进**：统一梳理阻塞调用，必要时改 async client 或线程池隔离，并给外部 IO 设置 timeout。

### 2.5 Swagger 文档与 Pydantic response_model 在你项目里解决了什么问题？

**结论**：Swagger 让 API 可发现、可调试；`response_model` 保证路由输出契约稳定，避免把内部模型或敏感字段直接返回。

**代码依据**：`api/routes/v1/sessions.py`、`media.py`、`auth.py` 都声明了 `response_model=ApiResponse[...]`，contract 定义在 `api/contracts/`。

**权衡**：强 contract 能减少前后端字段不一致；代价是 schema 变化要同步维护转换方法。

**生产级改进**：导出 OpenAPI 给前端生成 typed client，并在 CI 中检查 schema diff。

---

## 3. 认证与安全

### 3.1 你的 access token 和 refresh token 生命周期怎么设计？

**结论**：access token 短期有效，默认 900 秒；refresh token 较长，默认 14 天，并通过 HttpOnly cookie 存储。刷新时做 refresh token rotation，旧 token 被撤销，新 token 替换。

**代码依据**：配置在 `api/core/config.py` 的 `auth_access_token_ttl_seconds` 和 `auth_refresh_token_ttl_seconds`；签发在 `api/services/auth_service.py`；cookie 设置在 `api/routes/v1/auth.py`。

**权衡**：短 access token 降低泄露窗口，长 refresh token 保持用户体验。rotation 能减少重放风险，但需要数据库记录和并发控制。

**生产级改进**：增加设备维度、refresh token 家族检测、异常刷新告警和会话管理页。

### 3.2 为什么 refresh token 要存 hash，不直接存原文？

**结论**：refresh token 是长期凭证，数据库泄露时如果存原文，攻击者可以直接登录；存 hash 后只能比对，不能还原 token。

**代码依据**：`api/core/security.py` 的 `hash_refresh_token()` 使用 SHA-256；`api/services/auth_service.py` 保存和刷新时都只存 token hash；`api/db/auth_db.py` 的 `RefreshTokenRecord.token_hash` 是 unique/index。

**权衡**：hash 存储提升安全性，但无法展示原 token，也要求刷新请求必须带原 token 才能计算 hash。

**生产级改进**：可以加入 pepper、设备指纹和异常地理位置检测；对更高安全等级可考虑 token family replay detection。

### 3.3 refresh token rotation 如何防止重复使用？并发刷新会怎样？

**结论**：刷新时先查旧 token，确认未撤销且未过期，再用带 `revoked_at is null` 条件的 update 抢占撤销。并发刷新时只有一个请求能成功撤销旧 token，其他请求会失败。

**代码依据**：`api/db/auth_db.py` 的 `rotate_refresh_token()` 使用条件 update，并检查 `rowcount == 1`；成功后插入 replacement token。

**权衡**：这种方式能防止重复使用，但用户在多标签页同时刷新时，可能一个成功、一个收到认证失败，需要前端处理重试或重新登录。

**生产级改进**：引入短暂宽限窗口或 refresh single-flight，但要避免放大重放风险。

### 3.4 邮箱验证码为什么放 Redis 或内存 store，而不是直接放数据库？

**结论**：验证码是短生命周期、高频、可过期的数据，更适合 Redis TTL 或内存 store，不适合长期落数据库。数据库适合保存用户状态和可审计 token，不适合承载频控和 TTL 计数。

**代码依据**：`api/services/email_verification_store.py` 提供 `RedisEmailVerificationStore` 和 `InMemoryEmailVerificationStore`，验证码 key 设置 TTL，发送冷却和每日限制也在 store 中处理。

**权衡**：Redis TTL 简化过期清理，性能更好；内存 store 便于本地开发。代价是 Redis 不可用时注册验证链路会受影响，内存 store 不适合多实例生产。

**生产级改进**：生产必须使用 Redis，增加 Redis 健康检查和告警；验证码发送记录可以异步落审计表。

### 3.5 匿名 visitor owner 和登录 user owner 如何隔离资源？

**结论**：资源 owner 被统一编码成 `user:<id>` 或 `visitor:<id>`，匿名和登录用户的媒体、会话都按 owner_id 隔离。匿名用户通过 visitor cookie 延续身份。

**代码依据**：`api/common/deps.py` 的 `get_resource_owner()` 生成 owner；`api/common/ownership.py` 定义 `build_user_owner()`、`build_visitor_owner()` 和 storage path。

**权衡**：统一 owner_id 能让匿名和登录链路复用同一套 media/session 权限判断；代价是后续做“匿名数据合并到登录账户”时需要迁移 owner。

**生产级改进**：增加 visitor 到 user 的归并流程，并记录审计事件，避免历史资源丢失或错误归属。

### 3.6 为什么越权访问返回 NotFound，而不是 PermissionDenied？

**结论**：对资源型接口，越权返回 NotFound 可以避免暴露资源是否存在，降低 ID 枚举风险。用户只知道“这个资源不可访问或不存在”。

**代码依据**：`api/services/media_service.py` 的 `_ensure_owner()` 在 owner 不匹配时抛 `NotFoundError`；session service 也应遵循同类资源隐藏策略。

**权衡**：安全性更好，但调试时不如 PermissionDenied 直观。内部日志要记录真实原因，外部响应隐藏细节。

**生产级改进**：配合审计日志记录访问者、资源 id、owner mismatch，但响应仍保持 NotFound。

### 3.7 手写 JWT 相比使用成熟库有什么风险？

**结论**：手写 JWT 容易遗漏算法校验、时间校验、claim 校验、base64 边界和安全更新。当前实现只支持 HS256、签名校验和 exp/typ 检查，适合教学和原型，但生产建议换成熟库。

**代码依据**：`api/core/security.py` 自己实现 `_encode_jwt()`、`_decode_jwt()`、`create_access_token()` 和 `decode_access_token()`。

**权衡**：手写代码依赖少、便于理解；代价是安全维护压力大，容易错过 JWT 生态中的已知攻击面。

**生产级改进**：改用 PyJWT 或 Authlib，明确 issuer/audience、clock skew、key rotation 和算法白名单。

---

## 4. 配置与环境

### 4.1 `MODEL_RUNTIME_MODE=mock/live` 解决了什么工程问题？

**结论**：它把本地开发/测试和真实模型调用隔离开。mock 模式稳定、便宜、可重复；live 模式才要求真实 provider 配置。

**代码依据**：`api/core/config.py` 定义 `model_runtime_mode`；`api/modules/scene_engine/agent.py`、`coach_engine/agent.py`、`feedback_engine/agent.py` 都根据 mock/live 选择 provider。

**权衡**：mock 能保证开发速度和测试稳定，但不能代表真实模型质量；live 能验证真实链路，但成本和不确定性更高。

**生产级改进**：CI 默认 mock，预发布环境跑 live smoke；对 live 调用加超时、预算、日志和模型质量样本集。

### 4.2 `validate_runtime()` 在生产环境挡住了哪些事故？

**结论**：它在启动时阻止缺少关键配置的服务进入生产，例如默认 JWT secret、不安全 cookie、空 CORS、默认前端 URL、缺失 Deepgram 配置等。

**代码依据**：`api/main.py` 启动时调用 `settings.validate_runtime()`；具体校验在 `api/core/config.py`。

**权衡**：启动失败比带病运行更安全；代价是配置不完整时服务会直接不可用，需要部署前检查。

**生产级改进**：把配置校验加入 CI/CD 和部署前 smoke，并为不同环境提供 `.env.example` 和 secret manager。

### 4.3 `ALLOWED_ORIGINS`、secure cookie、JWT secret 分别有哪些生产风险？

**结论**：`ALLOWED_ORIGINS` 过宽会放大跨站调用风险；secure cookie 关闭会让 refresh token 在非 HTTPS 下传输；JWT secret 使用默认值会导致 token 可伪造。

**代码依据**：`api/main.py` 配置 CORS；`api/routes/v1/auth.py` 设置 refresh cookie；`api/core/config.py` 在 production 校验这些配置。

**权衡**：开发环境需要 localhost 和非 secure cookie；生产环境必须收紧。环境差异必须通过配置显式区分。

**生产级改进**：生产启用 HTTPS、精确 origin、secret manager、secret rotation 和 cookie domain/samesite 策略评估。

### 4.4 为什么 provider 配置允许 primary/fallback？

**结论**：AI provider 有超时、限流、格式错误和质量波动，primary/fallback 可以在主 provider 失败时切到备用 provider，提高可用性。

**代码依据**：`api/core/config.py` 有 `vision_primary_*`、`vision_fallback_*`、`text_primary_*`、`text_fallback_*`；scene 和 coach agent 都实现主备选择。

**权衡**：fallback 提高可用性，但可能带来质量、成本和延迟差异。还要避免 silent fallback 让问题长期不可见。

**生产级改进**：记录 provider 名称、耗时、失败原因和 fallback 命中率，按 provider 维度做告警和成本分析。

### 4.5 如果 live 模式只有 fallback provider，系统如何退化？

**结论**：当前设计允许 live 模式只有一个真实 fallback provider，此时 agent 会把 fallback 同时作为 primary 和 fallback 使用，系统仍能运行，但没有第二层容灾。

**代码依据**：`api/modules/scene_engine/agent.py` 和 `api/modules/coach_engine/agent.py` 在 live 模式下，如果没有 primary 但有 fallback，会将 resolved fallback 赋给 primary/fallback。

**权衡**：这种设计方便临时只接一个供应商，但可用性弱于真正主备。

**生产级改进**：在生产配置中强制至少两个 provider，或者明确把单 provider 运行标记为 degraded，并在健康检查中暴露。

---

## 5. 会话主链路

### 5.1 上传图片到开始会话的完整调用链是什么？

**结论**：图片先走 `/media/upload`，校验类型、大小和文件签名，上传到 R2 并保存 media 记录；开始会话时 `/sessions` 读取 media，签 R2 read URL，调用 scene engine 分析图片，再创建 session 和 opener message。

**代码依据**：上传入口在 `api/routes/v1/media.py`，业务在 `api/services/media_service.py`；开始会话入口在 `api/routes/v1/sessions.py`，编排在 `api/modules/session_engine/agent.py`。

**权衡**：先保存 media 再分析图片，可以把上传和模型分析解耦；代价是上传成功但后续建会话失败时，需要处理残留对象。

**生产级改进**：增加对象存储补偿删除、media 状态机、后台清理 orphan object 和链路 trace id。

### 5.2 `start_session` 为什么要先签 R2 read URL 再传给 scene engine？

**结论**：R2 私有桶不能直接暴露对象，scene engine/provider 需要一个临时可读 URL 才能分析图片。签名 URL 用 TTL 控制访问窗口。

**代码依据**：`SessionEngineAgent.start()` 调 `R2StorageService.async_create_signed_read_url()`，再把 signed URL 传给 `scene_engine.analyze()`。

**权衡**：签名 URL 避免公开桶，安全性更好；代价是 URL 有过期时间，模型调用必须在 TTL 内完成。

**生产级改进**：根据 provider 延迟设置 TTL，记录 URL 签发和使用失败；对支持直接上传 bytes 的 provider 可改为后端代理读取，减少 URL 暴露面。

### 5.3 `reply()` 中 feedback 和 coach 为什么可以 `asyncio.gather` 并发？

**结论**：feedback 只依赖 learner message、scene 和 vocab；coach reply 依赖 scene、role、历史和 learner message。两者互不依赖，所以可以并发生成，缩短单轮等待。

**代码依据**：`api/modules/session_engine/agent.py` 的 `reply()` 使用 `asyncio.gather()` 同时调用 `_review_with_context()` 和 `_respond_with_context()`。

**权衡**：并发降低延迟，但失败处理要谨慎。如果其中一个失败，不能只写半轮数据，否则会造成消息和 review 不一致。

**生产级改进**：给两个任务分别设置 timeout、provider trace 和降级策略，例如 feedback 失败时是否允许先返回 coach，需要产品明确。

### 5.4 并发生成失败时，为什么不能先写 learner message？

**结论**：因为一轮 reply 的语义是 user message、assistant message 和 review 一起形成完整回合。若先写 user message，再生成失败，历史里会出现没有回应和反馈的半轮状态。

**代码依据**：`SessionEngineAgent.reply()` 先完成 feedback 和 coach，再调用 `save_reply_turn()` 一次性落库。

**权衡**：延迟上会等两个生成都成功后才写库；好处是持久化状态始终完整。

**生产级改进**：如果要支持“用户消息已收到但 AI 稍后回复”，需要引入 pending 状态、异步任务和重试机制，而不是简单先写消息。

### 5.5 `save_reply_turn()` 如何保证一轮 user/assistant/review 原子落库？

**结论**：它在同一个 async DB session 和事务里读取当前 position，插入 learner message、assistant message，upsert review，更新 session 的 `updated_at`，最后一次 commit。任一步失败都会回滚。

**代码依据**：`api/db/session_db.py` 的 `SqlAlchemySessionRepository.save_reply_turn()`。

**权衡**：单事务保证一致性，但当前 position 用 `max(position)+1`，高并发同一 session 写入时需要额外约束或锁。

**生产级改进**：给 `(session_id, position)` 加唯一索引，对同一 session reply 做行级锁、乐观版本号或队列串行化。

### 5.6 语音 complete 为什么要做 transcript 去重？

**结论**：Deepgram 语音链路可能回传整段 transcript，其中包含已经存在于文本会话里的 opener 或历史消息。如果直接追加，会导致消息重复。

**代码依据**：`api/modules/session_engine/agent.py` 的 `_build_voice_messages()` 会跳过重复 opener，并用 `_find_tail_overlap()` 检测旧消息尾部和新 transcript 头部重叠。

**权衡**：去重能保护历史一致性，但基于 role/text 签名，遇到同一句话自然重复时可能需要更细的 turn id。

**生产级改进**：使用 Deepgram turn id、时间戳或客户端 sequence number 做幂等合并。

---

## 6. 数据库与事务

### 6.1 `SessionRecord` / `MessageRecord` / `ReviewRecord` 为什么拆表？

**结论**：session 是会话头信息，message 是多轮消息流，review 是会话复盘结果，三者生命周期和查询模式不同，拆表能减少冗余并提高查询效率。

**代码依据**：`api/db/session_db.py` 定义 `SessionRecord`、`MessageRecord`、`SessionReviewRecord`，还额外定义了 `SessionEventRecord` 和 `VoiceSessionFactRecord` 存运行时事件和语音事实。

**权衡**：拆表让列表页可以只查 session head，详情页再查 messages；代价是读完整详情时需要多次查询或 join。

**生产级改进**：为常用列表查询增加覆盖索引，必要时对历史列表做 read model 或缓存，避免每次加载大量消息。

### 6.2 `MessageRecord.position` 有什么作用？并发写入会不会冲突？

**结论**：`position` 表示消息在会话中的顺序，比按时间排序更稳定。并发写同一个 session 时，如果两个事务同时读到同一个 max position，可能产生冲突或乱序。

**代码依据**：`api/db/session_db.py` 的 `_load_messages()` 按 `position.asc()` 排序；`add_message()` 和 `save_reply_turn()` 用 `max(position)+1` 计算下一条位置。

**权衡**：position 简单直观，适合低并发单会话练习；但高并发下需要数据库约束和锁来保证唯一顺序。

**生产级改进**：增加 `(session_id, position)` unique index，并在写入时使用行锁、乐观版本号或按 session id 串行化队列。

### 6.3 cursor pagination 为什么用 `updated_at + id`，不是 offset？

**结论**：cursor pagination 在数据不断新增或更新时更稳定，性能也更好。`updated_at + id` 可以解决单纯时间戳重复时排序不唯一的问题。

**代码依据**：`api/db/session_db.py` 的 `list_user_sessions_page()` 按 `updated_at desc, id desc` 排序，游标是 `(updated_at, id)`；`api/modules/session_engine/agent.py` 负责把它编码成字符串。

**权衡**：cursor 适合无限滚动和历史列表，但不能直接跳到第 N 页。offset 简单，但大 offset 性能差，而且数据变化时容易重复或漏项。

**生产级改进**：为 `(user_id, updated_at, id)` 建复合索引，并明确 cursor 版本格式，方便以后扩展。

### 6.4 `list_user_sessions_page` 为什么 join review？

**结论**：历史列表只展示已经有 review 的完整练习，join review 可以过滤掉还没完成复盘的会话，避免列表出现半成品。

**代码依据**：`api/db/session_db.py` 的 `list_user_sessions_page()` 对 `SessionReviewRecord` 做 join，再按 user_id 和 cursor 查询。

**权衡**：join 能保证历史列表质量；代价是没有 review 的进行中会话不会出现。如果产品以后要展示“未完成会话”，需要单独查询。

**生产级改进**：明确会话状态机，例如 `active`、`review_ready`、`archived`，用 status 和 review 是否存在共同决定展示。

### 6.5 `save_session()` 先 flush 父 session 再写 message，是为了解决什么？

**结论**：这是为了解决严格外键校验下，子表 message 先写入而父表 session 还没落库导致的 FK 失败。flush 会先把父 session 发到数据库，但还没提交事务。

**代码依据**：`api/db/session_db.py` 的 `save_session()` 调 `_upsert_session_record()` 后立即 `await db_session.flush()`，注释也说明是为了严格 FK 数据库。

**权衡**：flush 保证同一事务内写入顺序正确，不破坏原子性；代价是需要理解 flush 和 commit 的区别。

**生产级改进**：配合迁移脚本和数据库约束测试，确保 PostgreSQL 和 SQLite 测试行为差异不会掩盖外键问题。

### 6.6 JSON 字段存 feedback、anchors、vocab 的优缺点是什么？

**结论**：JSON 字段适合存结构相对灵活、查询频率不高的 AI 输出，例如 feedback、visual anchors、vocab candidates。它能快速适配 schema 演进，但不适合复杂过滤和强约束。

**代码依据**：`api/db/session_db.py` 中 `visual_anchors`、`vocab_candidates`、`feedback`、`payload` 都是 JSON 字段。

**权衡**：JSON 减少早期 schema 迁移成本，适合 AI 输出迭代；代价是数据库层难以严格校验字段，复杂检索和统计成本更高。

**生产级改进**：稳定后把高频查询字段拆成列或子表；对 PostgreSQL 使用 JSONB 和 GIN 索引，但只给真实查询场景建索引。

### 6.7 PostgreSQL 上应给哪些字段建索引？为什么？

**结论**：至少给 owner/user、session 列表排序、消息分页、token 查询和事件查询建索引。索引要围绕真实 where/order by 设计，而不是给所有字段都建。

**代码依据**：当前 ORM 已给 `SessionRecord.user_id`、`media_id`、`status`、`updated_at`，`MessageRecord.session_id`，`RefreshTokenRecord.token_hash` 等字段设置 index。

**权衡**：索引能加速查询，但会增加写入成本和存储。会话系统读多写中等，列表和鉴权查询更值得优先优化。

**生产级改进**：建议增加 `(user_id, updated_at desc, id desc)`、`(session_id, position)`、`(session_id, created_at)`、`refresh_tokens(token_hash)` unique、`auth_action_tokens(token_hash)` unique，并结合 `EXPLAIN ANALYZE` 验证。

---

## 7. SQLAlchemy async

### 7.1 `create_async_engine` 为什么把 `postgresql://` 改成 `postgresql+psycopg://`？

**结论**：SQLAlchemy async engine 需要 async driver。很多平台提供的 URL 是标准 `postgresql://`，项目在创建 async engine 时自动改成 `postgresql+psycopg://`，让 SQLAlchemy 使用 psycopg 的 async 能力。

**代码依据**：`api/db/database.py` 的 `create_async_database_engine()` 检测 `postgresql://` 前缀并替换。

**权衡**：自动兼容部署平台的 DATABASE_URL，减少配置坑；代价是强绑定 psycopg async driver，依赖必须安装正确。

**生产级改进**：在环境校验中检查 driver 依赖，并在 README 或部署文档说明连接串兼容策略。

### 7.2 `expire_on_commit=False` 的作用是什么？

**结论**：提交后 ORM 对象属性不会自动过期，避免 commit 后访问属性又触发懒加载。在 async 场景里，这能减少 detached 或隐式 IO 问题。

**代码依据**：`api/db/database.py` 的 `create_session_factory()` 和 `create_async_session_factory()` 都设置了 `expire_on_commit=False`。

**权衡**：读取提交后的对象更方便；代价是对象可能不是数据库最新值，所以需要在关键写入后重新查询。

**生产级改进**：对写后读路径保持明确 reload，例如 `save_session()` commit 后再 `get_session()`，不要依赖旧 ORM 对象。

### 7.3 async session 每个方法开一个 session，有什么好处和代价？

**结论**：每个 repository 方法独立打开 session，事务边界清晰，不容易跨请求污染。代价是跨多个 repository 的原子事务比较难，需要额外设计 unit of work。

**代码依据**：`api/db/session_db.py` 中每个方法都 `async with self._session_factory() as db_session`。

**权衡**：当前会话写入大多能在单 repository 方法内完成，所以这种设计简单可靠。若未来一个业务动作要同时写 auth、media、session，就需要共享事务。

**生产级改进**：引入 Unit of Work 或 request-scoped session，并谨慎处理事务嵌套和回滚。

### 7.4 连接池参数 `pool_size/max_overflow/pool_timeout/pool_recycle` 怎么解释？

**结论**：`pool_size` 是常驻连接数，`max_overflow` 是高峰临时连接数，`pool_timeout` 是等连接的最长时间，`pool_recycle` 是连接回收时间，避免长期连接被数据库或网络断开。

**代码依据**：配置在 `api/core/config.py`，使用在 `api/db/database.py` 的 sync 和 async engine 创建逻辑里。

**权衡**：池太小会排队，太大会压垮数据库。FastAPI worker 数、请求并发和数据库最大连接数要一起算。

**生产级改进**：按压测结果设置池大小，并监控连接等待、连接使用率、慢查询和数据库 CPU。

### 7.5 SQLite 测试和 PostgreSQL 生产会有什么行为差异？

**结论**：SQLite 和 PostgreSQL 在并发、锁、JSON、时间类型、外键和事务隔离上都有差异。SQLite 适合轻量测试，但不能完全代表生产。

**代码依据**：`api/db/database.py` 对 sqlite 和非 sqlite 分别设置 connect args 和连接池参数；迁移目录在 `api/migrations/versions/` 面向真实数据库演进。

**权衡**：SQLite 让本地测试启动快、依赖少；但并发写和 JSON 查询等问题可能只在 PostgreSQL 暴露。

**生产级改进**：关键 repository 测试应在 PostgreSQL 容器上跑一层 integration test，特别是 refresh rotation、message position、cursor pagination 和 FK 行为。

---

## 8. AI Provider 与容错

### 8.1 scene engine 为什么要做低置信度门禁？

**结论**：低置信度图片即使能生成文本，也可能不适合口语练习。门禁能避免把不稳定或无视觉锚点的结果交给后续会话，保护用户体验。

**代码依据**：`api/modules/scene_engine/agent.py` 定义 `LOW_CONFIDENCE_THRESHOLD = 0.65`，并要求 `visual_anchors` 和 `vocab_candidates` 非空。

**权衡**：门禁提升质量，但会拒绝部分边界图片。产品上要给用户清晰重试提示。

**生产级改进**：基于真实样本调阈值，记录被拒图片的原因分布，必要时做可解释的图片质量建议。

### 8.2 provider 返回 invalid JSON 时，你怎么处理？

**结论**：provider 输出必须先经过 schema 校验，invalid JSON 或字段不符合 schema 要转成 provider error，再触发 fallback 或返回模型不可用。

**代码依据**：`scene_engine` 用 `SceneAnalysisResult.model_validate()` 校验 raw result；`feedback_engine` 的 `_load_json()` 解析 JSON，再用 `FeedbackResult.model_validate()` 校验。

**权衡**：强校验能保护下游，但会让模型偶发格式错误变成失败。fallback 能缓解可用性问题。

**生产级改进**：增加 JSON repair、重试一次、结构化输出 API、模型输出采样日志和 schema 版本。

### 8.3 primary provider 超时、fallback 成功时，用户会感知到什么？

**结论**：理想情况下用户只感知到一次稍慢但成功的响应，不需要知道发生了 fallback。系统内部要记录 primary 失败和 fallback 成功，方便排查质量和成本。

**代码依据**：`api/modules/scene_engine/agent.py` 和 `coach_engine/agent.py` 都优先调用 primary，失败后调用 fallback。

**权衡**：隐藏 fallback 能保持体验稳定；但如果不监控，团队可能不知道 primary 长期不可用。

**生产级改进**：响应可不暴露 provider，但日志和 metrics 必须包含 provider、耗时、错误类型和 fallback 命中率。

### 8.4 `UnsupportedSceneImageError` 和 `ModelProviderError` 为什么要区分？

**结论**：前者表示图片不适合练习，是用户可理解的问题；后者表示模型供应商或系统失败，是服务可用性问题。区分后才能给不同提示和告警。

**代码依据**：`api/modules/scene_engine/agent.py` 对低置信度或缺少 anchors/vocab 抛 `UnsupportedSceneImageError`，对 provider crash、invalid output 或主备都失败抛 `ModelProviderError`。

**权衡**：错误类型越清晰，前端体验和告警越精准；代价是需要维护异常体系，不能所有问题都抛 500。

**生产级改进**：错误响应增加 retryable、reason、support code，同时对 provider error 告警，对 unsupported 做产品统计。

### 8.5 prompt、schema、provider 分离有什么好处？

**结论**：prompt 管输出意图，schema 管结构契约，provider 管外部供应商调用。三者分离后，换模型、改提示词、改 API contract 都不会互相污染。

**代码依据**：各 engine 都有 `prompts/`、`schema.py`、`providers/` 或 provider client，例如 `api/modules/scene_engine/prompts/`、`schema.py`、`providers/vision_provider.py`。

**权衡**：结构清晰、可测试，但需要更多文件和接口适配。

**生产级改进**：为 prompt 建版本号和评估集，为 schema 建兼容策略，为 provider 建统一 timeout/retry/circuit breaker。

### 8.6 如果模型幻觉出不存在的视觉锚点，你怎么评估和修复？

**结论**：先用真实图片样本集评估 anchors 是否可见、是否适合练习，再从 prompt、schema、后处理规则和 provider 选择上修复。不能只靠主观看一两张图。

**代码依据**：`scene_engine` 已要求 `visual_anchors` 非空并有置信度门禁，但当前还需要更多真实样本评估，`docs/control/project-index.md` 也标记 scene engine 剩余真实样本验证。

**权衡**：严格过滤能减少幻觉，但可能降低通过率；宽松过滤能提高可用性，但会损害学习场景真实性。

**生产级改进**：建立标注集，记录模型输出和人工判定；引入二次校验、多模型交叉验证或对象检测辅助。

---

## 9. 媒体与对象存储

### 9.1 你如何校验上传文件是真的图片，而不是伪造 content-type？

**结论**：不能只相信 `content-type`，还要检查文件大小和文件头签名。当前实现对 JPEG、PNG、WebP 分别检查 magic bytes，伪造 content-type 但内容不匹配会被拒绝。

**代码依据**：`api/services/media_service.py` 的 `upload_media()` 依次调用 `_validate_content_type()`、`_validate_file_size()`、`_validate_file_signature()`。

**权衡**：magic bytes 校验比只看扩展名安全，但仍不是完整图片解码校验。它能挡住常见伪造，成本也低。

**生产级改进**：使用 Pillow 或 libmagic 做完整 MIME 识别，解码图片并限制像素尺寸，防止图片炸弹和异常编码。

### 9.2 为什么 storage key 要包含 owner 和日期？

**结论**：owner 用于资源隔离和后续清理，日期用于对象归档、排查和生命周期管理。这样 key 不只是随机字符串，还能表达数据归属和时间。

**代码依据**：`api/services/media_service.py` 的 `_build_storage_key()` 生成 `media/{owner}/{YYYY/MM/DD}/{media_id}-{safe_name}`；owner 转换在 `api/common/ownership.py`。

**权衡**：结构化 key 方便运维和批量清理；代价是 key 暴露了部分归属结构，所以桶必须私有，访问通过签名 URL。

**生产级改进**：配合对象 lifecycle policy、按 owner 删除、审计日志和孤儿对象清理任务。

### 9.3 R2 signed URL 的 TTL 如何取舍？

**结论**：TTL 要足够支撑前端预览和模型读取，但不能太长。当前默认 900 秒，适合短时间访问，降低 URL 泄露后的风险窗口。

**代码依据**：`api/core/config.py` 的 `r2_signed_url_ttl_seconds` 默认 900；`api/services/media_service.py` 和 `api/modules/session_engine/agent.py` 都使用该配置签 read URL。

**权衡**：TTL 太短会导致慢网络或模型延迟时 URL 过期；TTL 太长会增加泄露风险。

**生产级改进**：按用途拆分 TTL，例如前端预览 5-15 分钟、模型读取更短；记录签发原因和调用链。

### 9.4 上传成功但数据库保存失败，会产生什么脏对象？怎么补偿？

**结论**：对象已上传到 R2，但 media 记录没保存，会产生数据库不可见的 orphan object。当前主流程先上传再保存记录，因此这是需要补偿的风险点。

**代码依据**：`api/services/media_service.py` 先调用 `storage.async_upload_bytes()`，再构造 `Media` 并调用 `repository.save_media()`。

**权衡**：先上传再入库能确保数据库只记录已上传对象；代价是 DB 失败时要清理对象。反过来先入库则可能出现记录存在但对象上传失败。

**生产级改进**：失败时调用 `async_delete_object()` 补偿，或引入 `uploading/uploaded/failed` 状态机和后台清理任务。

### 9.5 私有桶、签名 URL、CDN 缓存之间怎么设计？

**结论**：原始图片应放私有桶，通过短期签名 URL 访问；CDN 可以缓存公开静态资源，但用户上传内容默认不应公开缓存。若要缓存，需要用授权边界和短 TTL 控制。

**代码依据**：`api/integrations/storage/r2.py` 使用 R2 presigned URL；`api/services/media_service.py` 暴露 `create_media_access_url()` 而不是 public URL。

**权衡**：私有桶安全性高，但每次访问都要签名；公开 CDN 性能好，但权限和隐私风险高。

**生产级改进**：对公开样例图和用户私有图分桶或分路径；私有图通过 signed URL 或 signed cookie，避免 CDN 长期缓存敏感内容。

---

## 10. Redis、RQ、限流与邮件

### 10.1 登录/注册限流 key 为什么包含 IP 和 subject？

**结论**：只按 IP 限流会误伤同一网络下的多个用户，只按邮箱又挡不住单 IP 扫大量邮箱。IP + subject 能同时限制来源和目标账号。

**代码依据**：`api/routes/v1/auth.py` 的 `_build_rate_limit_key()` 把 `request.client.host` 和 subject 拼成 key；`AuthRateLimiter.consume()` 按 action + key 计数。

**权衡**：组合 key 更精准，但仍可能受代理、NAT、IP 伪造影响。

**生产级改进**：接入真实反向代理 IP 解析、设备指纹、失败原因统计和 Redis 分布式限流。

### 10.2 Redis 实现验证码 TTL、发送冷却、每日限制分别用什么数据结构？

**结论**：验证码用 string JSON payload + TTL；发送冷却用 `SET key value EX seconds NX`；每日限制用按日期分桶的计数 key，`INCR` 后设置到上海时间次日零点过期。

**代码依据**：`api/services/email_verification_store.py` 的 `RedisEmailVerificationStore.issue_code()` 设置 code key、cooldown key、daily key。

**权衡**：这些都是 Redis 原生命令，简单高效；但多步操作存在部分失败风险，目前用 pipeline 批量写入一部分数据。

**生产级改进**：用 Lua 脚本把频控检查、计数和验证码写入做成原子操作，并增加 Redis 异常监控。

### 10.3 RQ 邮件队列比 FastAPI BackgroundTasks 强在哪里？

**结论**：RQ 是独立 worker + Redis 队列，任务不会依赖当前 Web 请求进程，支持重试、失败记录和横向扩展。BackgroundTasks 更适合轻量、短耗时、允许随进程丢失的任务。

**代码依据**：`api/services/auth_mail_queue.py` 发布任务到 `RedisQueue`；`api/integrations/queue/redis.py` 使用 RQ `Queue.enqueue()` 和 `Retry`。

**权衡**：RQ 增加 Redis 和 worker 运维成本，但邮件发送这种外部 IO 更适合队列化。

**生产级改进**：配置 dead letter、任务幂等 key、失败告警、worker 健康检查和发送审计。

### 10.4 邮件发送失败应重试几次？如何避免重复发送？

**结论**：当前 RQ 默认按 `[10, 30, 60]` 秒间隔重试 3 次。避免重复发送要靠任务幂等，例如同一 user/action/code 只允许一个有效任务，或者记录 delivery id。

**代码依据**：`api/integrations/queue/redis.py` 的 `DEFAULT_RETRY_INTERVALS = [10, 30, 60]`；邮件发送实现在 `api/services/auth_mailer.py`。

**权衡**：重试能处理临时 SMTP 抖动，但可能导致用户收到重复邮件。验证码场景中，重复发送旧 code 可能造成混乱。

**生产级改进**：加入邮件发送记录表，按 `delivery_id` 幂等；新验证码签发后旧验证码立即失效，并在邮件内容说明。

### 10.5 如果 Redis 挂了，注册验证链路应该 fail-open 还是 fail-closed？

**结论**：注册验证码和限流是安全边界，生产环境应 fail-closed，即 Redis 不可用时不发验证码或不允许验证通过。否则会绕过频控和验证码校验。

**代码依据**：`api/services/email_verification_store.py` 在配置 Redis 但依赖缺失时抛 `ConfigurationError`；`api/integrations/queue/redis.py` 在没有 `REDIS_URL` 或依赖时也抛配置错误。

**权衡**：fail-closed 会影响可用性，但保护账号安全；fail-open 体验好但容易被滥用。

**生产级改进**：Redis 高可用、限流降级开关、只读维护页和告警，而不是静默放开验证。

---

## 11. Deepgram 语音链路

### 11.1 voice bootstrap 返回哪些关键配置？

**结论**：bootstrap 返回 session id、Deepgram 临时访问 token、过期时间、WebSocket URL、agent settings 和当前 session。前端用这些配置建立实时语音会话。

**代码依据**：`api/modules/session_engine/agent.py` 的 `bootstrap_voice_session()` 构造 `VoiceBootstrapResult`；配置由 `api/integrations/deepgram/voice_agent.py` 的 `DeepgramSettingsBuilder.build()` 生成。

**权衡**：后端统一生成 settings 能保持角色、场景、history 和安全配置一致；代价是后端要维护 Deepgram 配置结构。

**生产级改进**：给 bootstrap 加设备能力探测、token 签发审计、失败重试和前端兼容性版本。

### 11.2 Deepgram token TTL 为什么要短？

**结论**：语音 token 是外部服务访问凭证，TTL 短能降低泄露风险，并限制单次语音会话生命周期。当前默认 600 秒。

**代码依据**：`api/core/config.py` 的 `deepgram_agent_token_ttl_seconds`；`DeepgramTokenIssuer.issue_token()` 调 Deepgram token grant。

**权衡**：TTL 短更安全，但长时间练习可能过期，需要前端刷新或重新 bootstrap。

**生产级改进**：根据会话时长做续期机制，续期也要校验 session owner，并记录异常签发频率。

### 11.3 think proxy 的认证边界在哪里？

**结论**：Deepgram think proxy 不是公开代理，必须带后端签发的 bearer token。后端解码 token，校验 token type，并限制请求 model。

**代码依据**：`api/routes/v1/deepgram.py` 的 `proxy_deepgram_think_chat_completions()` 提取 Authorization bearer；`DeepgramThinkProxyTokenCodec` 在 `api/integrations/deepgram/voice_agent.py` 中签发和解码服务 token。

**权衡**：代理能隐藏上游 API key，并控制模型和请求格式；代价是后端需要承接 Deepgram 到 LLM 上游的流量。

**生产级改进**：token claim 中加入 session owner、audience、rate limit，并记录每次 proxy 调用的 session id 和耗时。

### 11.4 SSE 代理时如何处理上游非 JSON / 非 SSE 响应？

**结论**：如果请求 streaming，只有上游返回 `text/event-stream` 才直接流式转发；如果是 JSON，就按 JSON 响应处理；其他 content-type 视为上游非法响应，返回 502。

**代码依据**：`api/routes/v1/deepgram.py` 的 `_stream_think_response()` 判断 `_is_sse_response()` 和 `_is_json_response()`，否则返回 `upstream_invalid_response`。

**权衡**：严格 content-type 能避免把 HTML 错误页或未知二进制透传给客户端；代价是对上游兼容性要求更高。

**生产级改进**：记录截断后的响应体摘要、request id 和 upstream status，便于排查供应商异常。

### 11.5 语音 transcript 和文本 session 合并时有哪些一致性问题？

**结论**：主要问题是重复消息、顺序错乱、最后一条用户发言缺失、语音中途断开和 review 与消息不一致。当前 complete 阶段会去重 transcript、提取最后一条用户发言并在一个事务里 finalize。

**代码依据**：`api/modules/session_engine/agent.py` 的 `complete_voice_session()`、`_build_voice_messages()`、`_find_latest_user_content()`；落库在 `api/db/session_db.py` 的 `finalize_voice_session()`。

**权衡**：complete 时统一合并能保持最终一致；但实时语音过程中数据库可能还没有每一轮中间状态。

**生产级改进**：引入 turn id、客户端 sequence、partial/final transcript 区分和幂等 complete token。

---

## 12. 测试与质量

### 12.1 你项目里后端测试分了哪些层？

**结论**：设计上分 smoke、module、integration、full_flow 四层；当前仓库控制面也按这些层记录测试门。实际代码层面，后端测试还处在补齐阶段，目前 `tests/` 中主要是 agent control 工具测试。

**代码依据**：`docs/control/project-index.md` 的“测试门”列出 smoke、module、integration、full_flow；当前 `tests/tools/test_agent_ops.py` 是已追踪测试文件。

**权衡**：测试门分层能让不同风险用不同成本验证；但当前业务测试不足，不能把“设计了测试层”说成“业务测试已经完整”。

**生产级改进**：补 API contract test、repository integration test、engine mock provider test 和 upload -> session -> reply -> review -> history 主链路测试。

### 12.2 哪些测试是单元测试，哪些是集成测试？

**结论**：单元测试应覆盖纯函数、schema 转换、prompt 输入组装、owner 生成、验证码 store 逻辑；集成测试应覆盖数据库 repository、FastAPI route、R2/Redis/Deepgram 适配和主链路。

**代码依据**：当前已存在的 `tests/tools/test_agent_ops.py` 更偏工具单元/控制面测试；业务层测试仍需补齐。

**权衡**：单元测试快、稳定，适合覆盖规则和边界；集成测试慢但能发现数据库、外部服务和路由串联问题。

**生产级改进**：用 mock provider 做稳定集成测试，用 skipif 控制 live 外部服务测试，CI 中至少跑 mock 主链路。

### 12.3 为什么 R2 live test 要 skipif？

**结论**：R2 live test 依赖真实 endpoint、bucket 和凭证，默认 CI 或本地环境不一定具备。`skipif` 能避免没有配置时测试失败，同时保留真实联调入口。

**代码依据**：R2 配置在 `api/core/config.py`，真实调用在 `api/integrations/storage/r2.py`。没有 `r2_endpoint` 或凭证时会抛 `StorageError`。

**权衡**：skipif 能保持常规测试稳定，但如果长期不跑 live test，真实集成可能漂移。

**生产级改进**：在预发布流水线配置真实 R2 secret，定期跑 live smoke，并限制测试对象路径和清理策略。

### 12.4 你如何 mock provider、repository、token issuer？

**结论**：项目通过构造函数注入依赖，测试时可以传入 fake provider、fake repository、fake token issuer，避免调用真实外部服务。

**代码依据**：`SessionEngineAgent.__init__()` 接收 `media_lookup`、`session_repository`、`read_url_signer`；`SceneEngineAgent.__init__()` 和 `CoachEngineAgent.__init__()` 接收 provider；`DeepgramTokenIssuer` 也可以用协议替代。

**权衡**：依赖注入让测试更稳定，但需要维护 fake 行为与真实接口一致。

**生产级改进**：建立统一 test doubles，例如 `FakeSessionRepository`、`FakeVisionProvider`、`FakeChatProvider`，并用 contract test 约束 fake 和真实实现。

### 12.5 目前最大测试缺口是什么？

**结论**：最大缺口是业务主链路和外部适配的系统级验证。当前代码有会话、认证、媒体、Deepgram 等实现，但缺少覆盖 upload -> start_session -> reply -> review -> history 的 backend-heavy 自动化测试。

**代码依据**：`docs/control/project-index.md` 明确 integration 和 full_flow 仍在 building/planned；当前 `tests/` 只有工具测试被追踪。

**权衡**：早期先搭主链路可以快速成型，但进入面试或演示阶段，必须补测试证明不是“只能手动跑通”。

**生产级改进**：优先补 mock 模式下的主链路 API test，再补 PostgreSQL repository test 和 live smoke。

### 12.6 面试官让你现场加一个回归测试，你会选哪个路径？

**结论**：我会选 `SessionEngineAgent.reply()` 或 `save_reply_turn()`，验证一轮 user/assistant/review 必须原子落库。这个路径能体现会话一致性，是项目的后端核心。

**代码依据**：业务逻辑在 `api/modules/session_engine/agent.py`，事务逻辑在 `api/db/session_db.py`。

**权衡**：这比测试简单工具函数更能体现工程价值；但现场时间有限，可以先用 fake repository 测 service 编排，再补数据库集成测试。

**生产级改进**：增加并发 reply 测试，覆盖 position 冲突和回滚行为。

---

## 13. 性能与扩展

### 13.1 单轮 reply 的瓶颈在哪里：DB、LLM、R2 还是网络？

**结论**：单轮文本 reply 的主要瓶颈通常是 LLM/provider 网络延迟，不是数据库。DB 只是读取 session 和写入两条 message + review；R2 只在 start_session 分析图片时明显参与。

**代码依据**：`SessionEngineAgent.reply()` 读取 session 后并发调用 coach 和 feedback provider，然后 `save_reply_turn()` 一次事务写库。

**权衡**：优化 DB 有价值，但优先级低于 provider 超时、并发、模型选择和 prompt 控制。

**生产级改进**：记录每段耗时：DB read、feedback、coach、DB write、总耗时；基于指标决定优化点。

### 13.2 如何把 session reply 延迟从 5 秒降到 2 秒？

**结论**：先测耗时，再优化 provider。当前已经用 `asyncio.gather` 并发 feedback 和 coach；下一步可以选择更快模型、缩短 prompt、设置 timeout、缓存静态上下文，必要时把 feedback 异步化。

**代码依据**：并发点在 `api/modules/session_engine/agent.py` 的 `reply()`；provider timeout 配置在 `api/core/config.py`。

**权衡**：把 feedback 异步化能降首包延迟，但用户可能先看到回复、后看到反馈，产品体验要重新设计。

**生产级改进**：引入 streaming、分阶段响应、模型路由、超时降级和 provider p95 监控。

### 13.3 如果同时 1000 人练习，先扩 FastAPI worker 还是扩数据库连接池？

**结论**：不能盲目先扩连接池。这个项目主要是外部 IO 和 LLM 等待，先看瓶颈指标：如果 worker 忙于等待 IO，可扩 worker 或异步能力；如果 DB 等连接严重，再调连接池。数据库连接池扩太大可能压垮 PostgreSQL。

**代码依据**：DB 连接池配置在 `api/core/config.py`，使用在 `api/db/database.py`；会话 reply 主要等待 provider。

**权衡**：worker 多能提高并发接入，但每个 worker 都可能持有连接池，乘起来会超过 DB 最大连接数。

**生产级改进**：按 `worker_count * pool_size + overflow` 计算上限，引入 PgBouncer、队列削峰和 provider 并发限制。

### 13.4 Python GIL 对这个项目影响大吗？

**结论**：影响不大，因为主链路主要是网络 IO：LLM、R2、Redis、Deepgram、数据库。GIL 主要影响 CPU 密集任务，本项目当前没有大量本地 CPU 推理。

**代码依据**：R2 调用用线程池包装同步 IO；session reply 使用 async 并发外部请求；数据库使用 async SQLAlchemy。

**权衡**：如果后续加入本地图片处理、音频特征提取或模型推理，GIL 和 CPU 才会明显影响吞吐。

**生产级改进**：CPU 密集任务放到独立 worker、进程池或专门推理服务，不要阻塞 FastAPI worker。

### 13.5 哪些任务适合异步队列，哪些必须同步返回？

**结论**：邮件发送、会话总结、图片离线分析、日志审计、发音评分后处理适合队列；登录、上传结果、开始会话、单轮 reply 的主响应通常要同步返回，除非产品改成异步任务状态。

**代码依据**：邮件队列在 `api/services/auth_mail_queue.py` 和 `api/integrations/queue/redis.py`；session 主链路在 `api/modules/session_engine/agent.py` 同步返回完整 session。

**权衡**：队列能削峰和重试，但增加状态查询和幂等复杂度。同步返回体验直接，但受外部服务延迟影响。

**生产级改进**：为长耗时任务设计 job id、状态机、幂等 key 和补偿流程。

---

## 14. 简历追问与反击题

### 14.1 这个项目最有技术含量的 3 个点是什么？

**结论**：第一是 AI engine 分层和 session orchestration；第二是认证、owner 隔离和 refresh rotation；第三是外部集成工程化，包括 R2、Redis/RQ、Deepgram 和 provider fallback。

**代码依据**：session orchestration 在 `api/modules/session_engine/agent.py`；认证在 `api/services/auth_service.py` 和 `api/db/auth_db.py`；外部集成在 `api/integrations/`。

**权衡**：这些点说明项目不是套 API，而是在处理真实后端系统的边界、失败和一致性问题。

**生产级改进**：把这些亮点用测试、监控和部署文档固化，否则面试官会认为只是代码结构好看。

### 14.2 你最想重构哪块？为什么现在没做？

**结论**：我最想重构的是事务边界和测试基础设施。现在 repository 每个方法自己开 session，简单可靠，但跨 repository 原子事务不够方便；测试也还没覆盖完整业务主链路。

**代码依据**：`api/db/session_db.py` 和 `api/db/auth_db.py` 各自管理 session；`docs/control/project-index.md` 标记 integration/full_flow 仍未完全收口。

**权衡**：项目早期优先打通主链路和模块边界，比一开始引入复杂 Unit of Work 更务实。现在进入集成阶段，才是补测试和事务抽象的合适时机。

**生产级改进**：引入 Unit of Work、PostgreSQL integration test、主链路 API test 和 provider fake contract。

### 14.3 如果生产事故：用户看到了别人的历史会话，你怎么定位？

**结论**：先止血，再定位 owner 边界。重点查鉴权解析、owner_id 生成、session 查询是否按 owner 过滤、历史接口是否漏了 owner 条件、缓存或前端状态是否串用户。

**代码依据**：owner 生成在 `api/common/deps.py` 和 `api/common/ownership.py`；历史和 session 查询通过 `SessionEngineService` 和 repository 完成；media 已有 `_ensure_owner()` 返回 NotFound 的模式。

**权衡**：这种事故属于高严重级别数据泄露，不能只修代码，要做影响范围分析和审计。

**生产级改进**：所有资源表统一 owner 字段和索引，所有资源读取必须走 owner-aware repository；增加审计日志、访问告警和回归测试。

### 14.4 如果模型成本暴涨，你如何限流、缓存、降级？

**结论**：先限流保护预算，再缓存可复用结果，最后做模型降级。具体包括用户级/ IP 级 reply 限流、scene 分析按 media_id 缓存、低成本 fallback 模型、mock/degraded 模式和每日预算开关。

**代码依据**：已有 auth 限流结构在 `api/services/auth_rate_limit.py`，可扩展到 session reply；provider primary/fallback 配置在 `api/core/config.py` 和各 engine agent。

**权衡**：限流会影响用户体验，缓存可能带来过期和隐私问题，降级模型可能降低质量。要按成本风险分级。

**生产级改进**：接入成本 metrics、provider 用量统计、用户配额、预算告警和按场景缓存策略。

### 14.5 如果面试官说“这就是套壳 AI”，你怎么证明工程价值？

**结论**：我会承认模型能力来自外部 provider，但项目价值在于把模型变成可用产品链路：图片存储、场景门禁、角色对话、反馈结构化、事务一致性、认证隔离、语音代理和可替换 provider。这些都是后端工程问题，不是简单转发 prompt。

**代码依据**：`api/modules/session_engine/agent.py` 展示编排；`api/modules/scene_engine/agent.py` 展示低置信度门禁和 fallback；`api/db/session_db.py` 展示原子落库；`api/services/auth_service.py` 展示认证安全；`api/integrations/deepgram/voice_agent.py` 展示语音集成。

**权衡**：AI 项目容易被质疑“套壳”，所以必须用模块边界、失败处理、数据一致性和测试策略证明工程含量。

**生产级改进**：补评估集、质量报告、成本报表、SLO 和线上观测，这些能进一步证明系统是可运营的 AI 产品，而不是 demo。
