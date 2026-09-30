# EchoWhale JD 面试准备：Python 后端方向

本文把截图中的 PHP 后端 JD 转成 Python/FastAPI 后端面试准备材料。回答时不要往 Laravel/Symfony 靠，直接讲 Python 后端、FastAPI、AI 工程、Redis/RQ、数据库、对象存储、实时语音和系统架构。

当前项目状态要如实表达：EchoWhale 后端主链路和模块结构已成型，系统仍处于 `integrating`，真实 Redis、SMTP、R2、Deepgram、LLM 等外部服务仍需要更完整的系统级 smoke，不能说已经生产发布。

## 1. JD 要求转 Python 后端能力画像

截图里的岗位核心要求可以翻译成以下 Python 后端能力：

- 核心业务系统开发：用 FastAPI 构建 API、服务层、数据访问层和 AI engine 编排，不只是 CRUD。
- AI / 数据能力：接入视觉模型、文本模型、语音服务，把模型结果转成稳定业务结构。
- 系统架构：模块拆分、接口契约、provider 抽象、mock/live 环境隔离、外部依赖适配。
- 高并发与性能优化：异步 IO、外部调用超时、并发任务、队列削峰、数据库连接池和分页。
- 数据库能力：SQLAlchemy、事务、一致性、索引、游标分页、JSON 字段、历史记录查询。
- Redis 与消息队列：验证码 TTL、发送冷却、每日限流、RQ 邮件队列、重试策略。
- 工程协作：分层职责、代码审查、测试分层、配置门禁、文档追踪。

## 2. EchoWhale 项目核心卖点

### 2.1 一句话介绍

EchoWhale 是一个情景式英语口语陪练系统：用户上传生活场景图片，系统识别场景并生成角色化对话，用户进行多轮英文练习后获得结构化反馈和历史复盘。

### 2.2 2 分钟项目介绍稿

EchoWhale 不是传统 CRUD demo，它的主链路是“图片上传 -> 私有对象存储 -> 场景理解 -> 对话教练 -> 学习反馈 -> 会话持久化 -> 历史复盘”。后端用 FastAPI 分层实现，路由层只处理 HTTP 入参和响应，service 层做权限和应用编排，modules 层拆出 `scene_engine`、`coach_engine`、`feedback_engine`、`session_engine`，db 和 integrations 层分别隔离持久化和外部服务。

我重点做了几个工程化点。第一是 AI engine 编排，`session_engine` 负责串联图片理解、对话生成和反馈生成，单轮 reply 中用 `asyncio.gather` 并发生成 coach reply 和 feedback，降低外部模型等待时间。第二是 provider 抽象，模型运行模式分成 mock/live，本地和测试可以稳定跑 mock，live 模式再校验真实 provider 配置。第三是外部系统接入，图片走 Cloudflare R2 私有存储和签名 URL，认证验证码走 Redis TTL 和频控，邮件发送走 RQ 队列，语音链路通过 Deepgram token 和 think proxy 接入。第四是安全和一致性，认证里有 access token、refresh token rotation、token hash 存储，资源通过 `user:<id>` 或 `visitor:<id>` 做 owner 隔离，会话消息和 review 在 repository 中用事务一起落库。

如果面试官追问生产化，我会明确说当前项目仍在 integrating 阶段，已经有模块边界和核心实现，但还需要补完整 backend-heavy 主链路测试、真实外部依赖 smoke、监控、成本统计和部署门禁。

## 3. 面试官最可能问的项目问题

### 3.1 这个项目为什么不是套壳 AI？

回答要点：

- 模型只是能力来源，项目价值在于把模型封装成稳定产品链路。
- EchoWhale 有媒体校验、私有存储、场景分析、角色对话、结构化反馈、会话事务、历史复盘、认证隔离和语音代理。
- 代码依据：
  - `api/modules/session_engine/agent.py`：会话编排。
  - `api/modules/scene_engine/`：图片场景理解。
  - `api/modules/coach_engine/`：对话生成。
  - `api/modules/feedback_engine/`：学习反馈。
  - `api/db/session_db.py`：消息、review、voice fact、event 落库。

### 3.2 你项目里最有技术含量的 3 个点是什么？

回答要点：

- AI engine 分层和 session orchestration：把多模态识别、对话和反馈拆成独立 engine。
- 外部依赖工程化：R2、Redis/RQ、Deepgram、LLM provider 都放在 integrations 或 provider 层。
- 安全和一致性：refresh token rotation、验证码频控、owner 隔离、会话 turn 原子落库。

### 3.3 如果新增一个“发音评分 engine”，你怎么设计？

回答要点：

- 新增 `api/modules/pronunciation_engine/`，只负责发音评分。
- `session_engine` 在语音 complete 后调用它，把评分结果写入 review 或独立 pronunciation record。
- 发音评分不应阻塞文本主链路；可用队列异步处理长音频。
- 需要定义输入输出 schema、置信度、音频片段引用、失败降级和幂等 complete token。

### 3.4 你会怎么解释项目架构？

回答要点：

- `routes`：HTTP 入参、依赖注入、响应模型。
- `services`：应用编排、权限校验、对外稳定接口。
- `modules`：AI 业务能力，包含 scene、coach、feedback、session。
- `db`：SQLAlchemy repository、事务、分页、模型转换。
- `integrations`：R2、Redis/RQ、LLM、Deepgram 等外部服务适配。
- 这样拆的原因是不同部分变化频率不同，模型、存储、HTTP contract、数据库演进不能耦合在一个 route 函数里。

### 3.5 面试官说“你这个项目生产不可用”，怎么回答？

回答要点：

- 先承认当前状态：项目处于 `integrating`，不是 `releasable`。
- 已完成的是模块边界、主要后端链路、外部适配入口和安全机制。
- 待补的是系统级 smoke、真实 provider/R2/Redis/SMTP/Deepgram 联调、监控告警、质量评估集、成本统计和 CI。
- 这样回答比硬说“已经上线可用”更可信。

## 4. Python / FastAPI / 异步底层追问

### 4.1 FastAPI 为什么适合这个项目？

回答要点：

- EchoWhale 大量等待外部 IO：LLM、R2、Redis、Deepgram、数据库。
- FastAPI 支持 async endpoint、依赖注入、Pydantic contract、OpenAPI 文档。
- 项目中 route 可以保持薄层，核心逻辑下沉到 service 和 modules。

### 4.2 Python GIL 对项目影响大吗？

回答要点：

- 当前影响不大，因为主链路是 IO 密集，不是 CPU 密集。
- 单轮对话主要瓶颈通常是模型 API 网络延迟，不是 Python 计算。
- 如果以后加入本地音频特征提取、图片预处理或本地模型推理，就要把 CPU 密集任务放进独立 worker、进程池或推理服务。

### 4.3 async def 里为什么不能直接跑阻塞 SDK？

回答要点：

- async 事件循环不能被阻塞，否则同 worker 内其他请求也会卡住。
- 项目里 R2 使用 boto3 这种同步 SDK，因此在 `api/integrations/storage/r2.py` 用 `run_in_threadpool` 包装。
- 生产中要给外部 IO 设置 timeout，并评估是否换 async client。

### 4.4 `asyncio.gather` 在项目里解决了什么问题？

回答要点：

- `SessionEngineAgent.reply()` 中 feedback 和 coach reply 互不依赖，所以并发执行。
- 这样单轮等待时间约等于两个模型调用中较慢的一个，而不是二者相加。
- 风险是任何一个任务失败都会影响整轮结果，需要超时、fallback 和错误归一化。

### 4.5 如果单轮 reply 从 5 秒优化到 2 秒，你怎么做？

回答要点：

- 先埋点拆耗时：DB read、coach provider、feedback provider、DB write、总耗时。
- 优先优化 provider：更快模型、缩短 prompt、timeout、fallback、缓存静态上下文。
- 产品允许时，可以把 feedback 异步化：先返回 assistant reply，再补反馈。
- 进一步可以做 streaming，让用户更早看到首包。

## 5. 消息队列、Redis 与异步任务追问

### 5.1 项目里哪里用了 Redis？

回答要点：

- 邮箱验证码存储：验证码 hash + TTL。
- 发送冷却：email 和 IP 维度 cooldown。
- 每日发送限制：按上海时区日期分桶计数。
- RQ 邮件队列：Redis 作为 broker。
- 代码依据：`api/services/email_verification_store.py`、`api/integrations/queue/redis.py`。

### 5.2 验证码为什么不直接存数据库？

回答要点：

- 验证码是短生命周期、高频、自动过期的数据，Redis TTL 更合适。
- 数据库适合存用户状态、refresh token、审计记录，不适合承担大量临时计数和过期清理。
- 生产环境 Redis 不可用时，验证码和限流应 fail-closed，避免绕过安全边界。

### 5.3 Redis 验证码有哪些 key？

回答要点：

- `auth:verify_code:{email}`：验证码 payload，包含 code hash、剩余尝试次数、创建时间。
- `auth:verify_send:cooldown:{scope}:{value}`：发送冷却，scope 可以是 email 或 IP。
- `auth:verify_send:daily:{scope}:{value}:{yyyymmdd}`：每日发送次数。
- 发送频控同时看 email 和 IP，避免只按单一维度限流被绕过。

### 5.4 RQ 比 FastAPI BackgroundTasks 强在哪里？

回答要点：

- RQ 是独立 worker + Redis 队列，请求进程挂了任务也不会跟着丢。
- 支持重试、失败记录和横向扩展，更适合 SMTP 这种外部 IO。
- 当前 `RedisQueue` 默认按 `[10, 30, 60]` 秒重试。
- BackgroundTasks 更适合轻量、短耗时、丢失影响小的任务。

### 5.5 邮件队列如何避免重复发送？

回答要点：

- 当前有重试机制，但生产还应补幂等。
- 可以引入 delivery id、邮件发送记录表，或者按 user/action/code 保证同一验证码只对应一个有效任务。
- 新验证码签发后旧验证码应失效，避免用户收到多封邮件时不知道哪个有效。

### 5.6 哪些功能适合放队列？

回答要点：

- 适合队列：邮件发送、会话总结、离线图片分析、发音评分后处理、审计日志、模型质量评估。
- 不适合默认队列：登录、上传返回、开始会话、单轮实时 reply，除非产品改成 job 状态查询。
- 队列化带来的新问题：job id、任务状态、幂等、重试、死信、失败告警。

## 6. 数据库、事务和架构追问

### 6.1 会话数据怎么设计？

回答要点：

- `sessions` 保存会话头：用户、媒体、场景、角色、状态、视觉锚点、候选词、时间。
- `session_messages` 保存消息流：session、position、role、text、feedback。
- `session_reviews` 保存复盘结果。
- `session_events` 和 `voice_session_facts` 保存语音链路运行时事实。
- 代码依据：`api/db/session_db.py`。

### 6.2 单轮 reply 为什么要事务？

回答要点：

- 一轮 reply 至少包含用户消息、assistant 消息和 review 更新。
- 如果只写入用户消息但 assistant/review 失败，历史记录会不一致。
- `save_reply_turn()` 在同一个 DB session 中写两条 message、upsert review、更新 session 时间，再 commit。

### 6.3 历史分页为什么用 cursor，不用 offset？

回答要点：

- offset 在数据量大时越翻越慢，而且新增数据会导致翻页漂移。
- 项目历史会话按 `updated_at desc, id desc` 排序，用 `(updated_at, id)` 作为游标。
- 同时间戳用 id 做稳定 tie-breaker。
- 代码依据：`list_user_sessions_page()` 和 `_encode_history_cursor()`。

### 6.4 数据库索引会怎么设计？

回答要点：

- `sessions.user_id`：按用户查历史。
- `sessions.updated_at`：历史排序和分页。
- `sessions.media_id`：按媒体关联会话。
- `session_messages.session_id`：读取会话消息。
- `session_events.session_id/event_type/stage/created_at`：排查语音和运行时事件。
- refresh token hash 要 unique/index，支持快速查找和 rotation。

### 6.5 如果两个请求同时 reply 同一个 session，会有什么风险？

回答要点：

- 风险是 position 冲突、消息顺序错乱、review 被后提交请求覆盖。
- 当前 `save_reply_turn()` 会读取当前最大 position 再追加，适合普通场景，但高并发同 session 还需要更强控制。
- 生产改进可以加 session 级乐观锁、version 字段、数据库唯一约束 `(session_id, position)`、或者同 session reply 串行队列。

### 6.6 为什么会话消息不都塞在 sessions 的 JSON 里？

回答要点：

- 消息独立成表更适合分页、统计、审计和后续搜索。
- JSON 全塞在 session 中写放大严重，也不利于大历史会话分页。
- 当前只有 visual anchors、vocab candidates、feedback 这类结构化小对象用 JSON 字段。

## 7. AI 工程和模型接入追问

### 7.1 scene / coach / feedback 为什么要拆开？

回答要点：

- scene 负责“图片变成可练习场景”。
- coach 负责“按角色自然接话和推进对话”。
- feedback 负责“语法、自然表达、词汇建议”。
- session 负责“把三者串起来并持久化”。
- 拆开后可以独立替换模型、prompt、schema 和测试样本。

### 7.2 `MODEL_RUNTIME_MODE=mock/live` 有什么价值？

回答要点：

- mock 模式适合本地开发和 CI，稳定、便宜、可重复。
- live 模式才要求真实 provider 配置，用于预发布和真实联调。
- 避免测试依赖外部模型波动，也避免无意中消耗真实 API 成本。

### 7.3 provider primary/fallback 怎么设计？

回答要点：

- AI provider 可能超时、限流、返回格式不稳定或质量波动。
- primary/fallback 允许主 provider 异常时切备用 provider。
- 生产中不能 silent fallback，必须记录 provider、耗时、错误原因、fallback 命中率和成本。

### 7.4 场景理解结果如何保证可用？

回答要点：

- 输出不应是自由文本，而应是结构化字段：scene、role、opener、visual anchors、vocab candidates、confidence 等。
- 低置信度、图片不可用、模型失败要有业务错误或 fallback。
- 这样前端和 session engine 才能稳定消费。

### 7.5 AI 项目的测试怎么做？

回答要点：

- 单元测试覆盖 schema、prompt 输入组装、规则工具、owner 生成、验证码 store。
- mock provider 集成测试覆盖 upload -> start_session -> reply -> review -> history。
- live smoke 只在配置齐全的预发布环境跑，避免 CI 不稳定。
- 还应准备模型质量样本集，评估场景识别、对话自然度和反馈质量。

### 7.6 如果模型返回 JSON 格式错了怎么办？

回答要点：

- provider 层负责解析和校验，不能把坏格式直接传给业务层。
- 失败时可以重试、fallback 或返回业务错误。
- 生产中要记录原始响应摘要，但注意脱敏和长度限制。

## 8. 安全、认证和权限追问

### 8.1 access token 和 refresh token 怎么设计？

回答要点：

- access token 短期有效，默认 900 秒。
- refresh token 长期有效，默认 14 天，通过 HttpOnly cookie 保存。
- refresh 时做 rotation：旧 token 撤销，新 token 替换。
- 代码依据：`api/services/auth_service.py`、`api/db/auth_db.py`、`api/core/config.py`。

### 8.2 refresh token 为什么存 hash？

回答要点：

- refresh token 是长期凭证，数据库泄露时不能让攻击者拿到原文直接登录。
- 存 hash 后只能比对，不能还原 token。
- 生产中还可以加入 pepper、设备维度和 token family replay detection。

### 8.3 owner 隔离怎么做？

回答要点：

- 资源 owner 统一编码成 `user:<id>` 或 `visitor:<id>`。
- media、session、history 查询都要校验 owner。
- 越权读取资源返回 NotFound，避免暴露资源是否存在。
- 代码依据：`api/common/ownership.py`、`api/services/media_service.py`、`api/modules/session_engine/service.py`。

### 8.4 为什么越权返回 NotFound？

回答要点：

- 防止 ID 枚举，外部只知道资源不可访问或不存在。
- 内部日志和审计可以记录真实原因。
- 这是资源型接口常见安全策略。

### 8.5 生产环境配置门禁有哪些？

回答要点：

- JWT secret 不能用默认值。
- secure cookie 必须开启。
- CORS origin 不能空或过宽。
- 前端 public URL、Deepgram 配置等必须显式设置。
- `settings.validate_runtime()` 在启动时校验，宁可启动失败，也不要带病运行。

## 9. R2、媒体上传和对象存储追问

### 9.1 图片上传链路是什么？

回答要点：

- route 接收文件。
- `MediaService` 校验 content type、文件大小、文件签名。
- 构造 owner-aware storage key。
- 上传到 R2。
- 保存 media 元数据。
- 返回短期 signed read URL。
- 代码依据：`api/services/media_service.py`、`api/integrations/storage/r2.py`。

### 9.2 为什么用私有桶和 signed URL？

回答要点：

- 用户上传图片可能有隐私，不适合长期公开 URL。
- signed URL 有过期时间，可以控制访问窗口。
- 缺点是每次访问要签名，CDN 缓存策略也要更谨慎。

### 9.3 文件安全怎么做？

回答要点：

- 只允许 jpeg/png/webp。
- 限制最大文件大小。
- 不只信 content type，还检查文件魔数。
- 文件名做 sanitize，storage key 按 owner 和日期组织。
- 生产中还要补病毒扫描、图片解码安全、对象清理和审计。

### 9.4 上传成功但建会话失败怎么办？

回答要点：

- 当前上传和会话创建是两个步骤，上传成功但分析失败可能留下 media 对象。
- 生产改进可以加 media 状态机、orphan object 清理、失败补偿删除、链路 trace id。

## 10. Deepgram 语音链路追问

### 10.1 voice bootstrap 做了什么？

回答要点：

- 校验 session owner。
- 签发 Deepgram 临时 token。
- 返回 WebSocket URL、agent settings、session 信息。
- 保存 voice session fact 和 event，标记语音链路启动。
- 代码依据：`api/modules/session_engine/agent.py`。

### 10.2 Deepgram token TTL 为什么要短？

回答要点：

- 语音 token 是外部服务访问凭证，TTL 短能降低泄露影响。
- 当前默认 600 秒。
- 长练习场景需要续期机制，续期也必须校验 session owner。

### 10.3 think proxy 的安全边界是什么？

回答要点：

- 代理不是公开接口，必须带后端签发的 bearer token。
- 后端校验 token，再限制上游模型。
- 这样能隐藏上游 API key，并防止客户端任意请求模型。
- 代码依据：`api/routes/v1/deepgram.py`。

### 10.4 SSE 代理怎么处理异常响应？

回答要点：

- streaming 请求只有上游返回 `text/event-stream` 才流式转发。
- JSON 响应按 JSON 处理。
- 非 JSON / 非 SSE 响应返回 502，避免把 HTML 错误页或未知内容透传给客户端。

### 10.5 语音 transcript 合并有什么一致性问题？

回答要点：

- 可能重复消息、顺序错乱、最后用户发言缺失、中途断开、review 与消息不一致。
- 当前 complete 阶段会做 transcript 去重，提取最后一条 user 发言，生成 feedback 和 review，再事务化 finalize。
- 生产改进可以加 turn id、sequence、partial/final 标识和幂等 complete token。

## 11. 高并发、性能和稳定性追问

### 11.1 1000 人同时练习，瓶颈在哪里？

回答要点：

- 先不要猜，先看指标。
- 常见瓶颈会是外部 provider 并发和延迟，其次是 FastAPI worker、数据库连接池、Redis、R2。
- 不能盲目扩大 DB 连接池，因为 `worker_count * pool_size + overflow` 可能压垮 PostgreSQL。

### 11.2 如何做削峰？

回答要点：

- 非实时任务放队列：邮件、总结、离线分析、发音评分。
- 实时 reply 加用户级/IP 级限流和 provider 并发限制。
- 对长耗时任务返回 job id，前端轮询或订阅状态。

### 11.3 如何做降级？

回答要点：

- provider fallback。
- feedback 异步化或临时关闭详细反馈。
- scene 分析按 media_id 缓存。
- 达到成本阈值后切低成本模型或限制频率。
- 外部服务不可用时返回明确 degraded 状态，不静默假装成功。

### 11.4 如何监控这个项目？

回答要点：

- API 层：请求量、错误率、p95/p99 latency。
- provider 层：模型耗时、失败率、fallback 命中率、token 成本。
- DB 层：连接池等待、慢查询、事务失败。
- Redis/RQ：队列长度、失败任务、重试次数。
- 业务层：上传成功率、会话创建成功率、reply 成功率、review 生成成功率。

## 12. 项目短板与生产化改进回答

面试中被问短板时，可以主动说这些：

- 测试缺口：当前业务主链路自动化测试仍需补齐，尤其是 upload -> session -> reply -> review -> history。
- 外部联调：真实 R2、Redis、SMTP、Deepgram、LLM provider 还需要系统级 smoke。
- 观测缺口：需要 request id、trace、provider metrics、成本统计和错误告警。
- 并发缺口：同 session 并发 reply 需要 session 级锁、乐观锁或唯一约束保护。
- 队列缺口：邮件任务需要更完整的幂等、dead letter 和发送审计。
- AI 质量缺口：需要固定样本集评估 scene、coach、feedback 的质量，而不能只看人工体验。

推荐回答方式：

> 我不会把当前项目说成已经生产级完备。它现在更像一个后端主链路和 AI 工程边界比较完整的作品，已经能体现架构、编排、安全和外部系统接入能力。下一步生产化重点是测试、联调、监控、成本和并发一致性。

## 13. 简历表述建议

可以写：

- 基于 FastAPI 设计情景式英语 AI 陪练系统，完成图片上传、场景理解、多轮对话、学习反馈和历史复盘主链路。
- 拆分 `scene_engine`、`coach_engine`、`feedback_engine`、`session_engine`，实现 AI 能力模块化和 session orchestration。
- 设计 mock/live provider 运行模式，隔离本地测试与真实模型调用，支持主备 provider 扩展。
- 接入 Cloudflare R2 私有对象存储，使用短期签名 URL 控制用户图片访问。
- 实现邮箱验证码、Redis TTL/频控、RQ 邮件队列和 refresh token rotation，提升认证链路安全性。
- 接入 Deepgram 实时语音链路，支持 token bootstrap、think proxy 和 transcript finalize。
- 使用 SQLAlchemy 维护 session/message/review/event 持久化，支持游标分页和会话复盘查询。

避免写：

- “已上线生产环境并稳定支撑大规模用户”，除非真实完成部署和验证。
- “自研 AI 模型”，当前项目是 provider 接入和 AI 工程编排，不是模型训练平台。
- “完整微服务架构”，当前是模块化单体后端，不是多服务拆分。

## 14. 快速背诵版问题清单

项目架构：

- 你用 2 分钟介绍 EchoWhale。
- 为什么这个项目不是 CRUD demo？
- routes、services、modules、db、integrations 怎么分层？
- scene/coach/feedback/session 四个 engine 边界是什么？
- 如果新增发音评分，放哪一层？

Python/FastAPI：

- FastAPI 为什么适合这个项目？
- async def 和普通 def 怎么选？
- GIL 对这个项目影响大吗？
- `asyncio.gather` 在 reply 里解决了什么？
- 同步 boto3 为什么要放线程池？

Redis / MQ：

- 验证码为什么用 Redis？
- cooldown、daily limit、code TTL 分别怎么实现？
- RQ 比 BackgroundTasks 强在哪里？
- 邮件任务如何重试和幂等？
- Redis 挂了应该 fail-open 还是 fail-closed？

数据库：

- session/message/review 表怎么设计？
- 单轮 reply 为什么要事务？
- cursor pagination 为什么比 offset 更适合历史页？
- 同 session 并发 reply 有什么风险？
- 哪些字段需要索引？

AI 工程：

- mock/live 模式解决了什么问题？
- provider fallback 怎么设计？
- 模型返回格式错误怎么处理？
- 如何做 AI 质量评估？
- 如果模型成本暴涨，如何限流、缓存、降级？

安全：

- access token 和 refresh token 生命周期怎么设计？
- refresh token 为什么存 hash？
- refresh token rotation 如何防重放？
- owner 隔离怎么做？
- 越权为什么返回 NotFound？

语音与外部服务：

- Deepgram bootstrap 返回什么？
- think proxy 如何保护上游 API key？
- SSE 代理如何处理非 SSE 响应？
- transcript 合并有哪些一致性问题？
- R2 signed URL 为什么比 public URL 更安全？

生产化：

- 当前离 releasable 还差什么？
- 如何做监控和 tracing？
- 1000 人同时练习先扩什么？
- 最大测试缺口是什么？
- 面试官质疑“套壳 AI”时怎么回应？
