# EchoWhale PRD（v0.5）

> 本文档描述产品**当前形态**（v0.5，2026-10-03 对齐代码重写）。历史演进记录在
> [docs/versions/](versions/README.md)，批次进度与决策见 docs/features/ 各 feature 文档；
> PRD 不做 changelog。对外协议层文档见 [api.md](api.md)，部署运行手册见
> [deployment.md](deployment.md)。

## 1. 项目概述

### 1.1 项目定位

EchoWhale 是一个面向日常口语初中级学习者的情景式英语陪练系统。用户上传一张日常生活图片（或选择内置示例场景）后，系统识别图片中的场景和关键物体，基于该场景发起一段角色化英语对话；用户可以打字（流式回复）或直接开口（实时语音），每轮收到简洁、可操作的学习反馈，练习结束后获得本轮复盘，并沉淀个人学习档案。

本项目已实现：

- 一个可在线演示的开源作品
- 一个具备完整用户链路的 AI 教育产品原型（注册/登录、练习、档案、历史）
- 一个适合写入简历、能体现全栈 + AI 工程能力的项目

### 1.2 核心价值

- 把“看图识物”升级成“基于真实场景开口练英语”
- 把 AI 对话从泛聊天变成有明确语境的口语训练
- 把反馈从长篇解释收敛成用户真正能立刻吸收的建议
- 练习产生数据：错误画像、CEFR 水平、场景频次滚动沉淀，反哺后续每一轮的教练与反馈

### 1.3 目标用户

- 日常口语初中级英语学习者
- 想提升实际开口能力，而不是只背单词和语法的人
- 需要轻量、高频、真实语境练习的学生或职场新人

## 2. 产品目标

### 2.1 MVP 目标（已达成）

第一版目标：

> 用户上传一张生活场景图片后，能够在 3 分钟内完成一轮完整的英语情景对话练习，并收到简洁反馈。

该目标已随 v0.3 交付达成，并在此基础上持续演进：流式回复、实时语音练习、学员档案、LLM 复盘均已上线（见 §4）。

### 2.2 成功标准

- 用户能成功上传图片（或选择示例场景）并创建会话
- 系统能稳定给出一个合理场景和角色设定，并以服务端下发的展示文案呈现
- 用户至少完成 3 轮英文对话
- 每轮回复后都能获得结构化反馈
- 会话历史可回看，练习结束有复盘
- 认证用户的练习过程滚动沉淀为个人学习档案

### 2.3 非目标

以下能力明确不在当前范围：

- 发音打分（语音链路已上线，但只做听写转写与对话收口，不对发音质量评分）
- 本地模型训练与微调平台
- 复杂课程系统和付费体系
- 多角色群聊或多 Agent 协作可视化

## 3. 核心用户流程

### 3.1 主流程（文字练习）

1. 用户进入首页，上传一张场景图片，或直接选择内置示例场景（咖啡店 / 办公室 / 街头问路，由后端预设下发）
2. 图片路径：系统识别场景与关键物体，生成角色身份和开场白
   - 若场景分析已开启异步且缓存未命中，接口返回 `202`（状态“分析中”），前端轮询场景分析状态端点，就绪后重试创建会话
3. 用户用英文回复
4. 系统流式输出（SSE）：先下发本轮反馈卡片，再逐段下发教练回复，最后下发会话最新状态
5. 每轮反馈包含：语法纠错、更自然表达、推荐词汇、下一步建议
6. 用户继续多轮练习；认证用户的错误画像、CEFR 估计、场景频次随轮滚动更新
7. 会话结束后查看本轮复盘；历史记录可回看

### 3.2 语音练习流程

1. 用户在会话内启动语音练习，后端签发受限的 Deepgram 会话令牌与 Agent 配置
2. 语音 Agent 实时听写并对话，思考（think）模型调用经后端代理（按会话维度限流）
3. 练习结束后收口：转写回传去重入库，生成反馈与复盘，语音事实与诊断事件落库

### 3.3 示例场景

示例场景由后端下发（预设见 [sample_presets.py](../api/modules/session_engine/sample_presets.py)，展示文案单一事实源见 [review_builder.py](../api/modules/session_engine/review_builder.py)）：

- 咖啡店点单（coffee → coffee_shop / friendly barista）
- 办公室日常沟通（office → office / project teammate）
- 街头问路（street → travel / helpful passerby）

## 4. 功能需求

### 4.1 图片上传与媒体管理

- 支持上传 jpeg / png / webp，单文件上限 10MB（流式校验，超限或类型不符返回 413 / 415）
- 全局请求体上限 12MB（含 multipart 编码余量），超限返回统一信封 413
- 文件直传 Cloudflare R2（已接入），返回媒体 ID 与元数据，读访问走签名 URL（TTL 900 秒）
- 媒体归属与请求方身份绑定，越权访问一律收敛为 404

### 4.2 场景理解模块

- 输入：图片签名 URL（或示例场景预设）
- 输出：场景类型、角色设定、开场白、视觉锚点、教学词汇候选、置信度
- 视觉模型主备双通道，主通道失败自动切换备通道
- 分析结果按媒体 ID 缓存并携带提示词版本；版本不一致或损坏自愈为重分析
- 异步模式（`SCENE_ANALYSIS_ASYNC_ENABLED`）：分析任务入 RQ 队列，创建会话返回 202，客户端轮询状态端点；队列缺席时自动降级为内联分析
- 非场景图片返回明确错误（1007 / 422）

### 4.3 对话教练模块

- 根据场景、角色与最近窗口（8 轮）生成回应，保持角色一致性与多轮推进
- 每轮只推动一个明确交流目标；对话风格简洁、自然、可继续追问
- 学员档案（上下文注入块 + CEFR 估计）注入教练提示词，实现个性化难度与话术
- 模型输出有 2000 字符硬顶，超长截断并留观测日志
- 教练分支失败时整轮失败、不落任何消息（回复是主价值）

### 4.4 学习反馈模块

- 每轮至少输出 3 类反馈：`Grammar` / `More Natural` / `Useful Words`，另有 `Next Step` 供复盘卡片消费
- 错误归类采用 9 类封闭集合（grammar / tense / article / preposition / word_choice / collocation / register / spelling / other），集合外的模型幻觉值在写侧丢弃
- 反馈必须短，不做大段讲解
- 反馈分支失败时降级为占位反馈（如实标注本轮失败），本轮照常返回与落库

### 4.5 会话编排模块

- 串联场景理解、对话教练、学习反馈与复盘；管理多轮消息记录与会话状态
- 反馈与教练并发执行、互不拖累；回复轮消息原子化落库（position 唯一约束兜底并发写）
- 流式路径：客户端断连时取消语义正确传播，失败轮次不落库

### 4.6 流式回复（SSE）

- `POST /sessions/{id}/reply/stream` 以 `text/event-stream` 下发事件：`feedback` → `delta*` → `session`
- 开流前的错误（鉴权 / 限流 / 不存在）仍走统一信封与 HTTP 状态码；开流后的错误以 `error` 事件下发（与信封同构）
- 与普通回复共用同一限流配额

### 4.7 语音练习（Deepgram 实时语音 Agent）

- `voice/bootstrap`：签发受限语音令牌（TTL 600 秒）与 Agent 配置（听写模型、音色、思考模型白名单等）
- `deepgram/think/chat/completions`：思考模型代理，按会话维度限流（120 次 / 5 分钟），支持 SSE 流式透传；错误为 OpenAI 风格（不走统一信封）
- `voice/complete`：转写收口——尾段去重入库、生成反馈与复盘、语音事实与客户端诊断落库
- 令牌签发失败返回 1302 / 503

### 4.8 学员档案

- 仅认证用户建档（visitor 会话不产生任何档案读写）；每用户一行，三个 JSON 字段全部写侧封顶、行宽不随练习轮数增长
- 内容：CEFR 滚动估计（最近 10 次观测取下中位）、错误画像（9 类封闭集合计数）、场景练习频次（最近 12 个场景）
- 注入教练与反馈提示词（上下文行 + CEFR 等级），也作为语音 Agent 思考提示词的个性化来源
- 读侧闭环：`GET /api/v1/learners/me/profile` 只读下发档案（认证必需；空档案返回 200 全空载荷而非 404）。错误类型 top 3 携带服务端中文展示名；场景以服务端映射后的展示名为键（任何路径不外露原始 scene id），同名展示场景计数合并，载荷封顶 top 3 错误 / 12 场景。前端 `/progress` 进度页（RequireAuth）渲染水平估计、常见错误、练习场景与累计轮数，空态引导开始第一次练习（见 [api.md](api.md) §12 与 docs/features/learner_profile_progress）
- 档案读写是增强分支：任何失败只降级记日志，绝不拖垮回复轮（该语义仅限回复轮写路径；档案读 API 对存储故障如实返回 500 信封，不伪装成空档案）

### 4.9 LLM 复盘

- 每轮生成短中文复盘文案（亮点 / 下一试 / 下一步），随会话响应下发；会话维度复盘接口聚合返回
- 复盘是增强分支：与教练流并行、有界等待（5 秒），超时 / 失败 / mock 模式一律降级为模板复盘
- 复盘文案逐字段截断硬顶（REVIEW_COPY_MAX_CHARS，五字段校验层生效），防失控输出撑爆卡片

### 4.10 场景文案服务端下发

- 场景展示名（`scene_title`）与角色标签（`role_label`）由后端单一事实源下发（预设文案或自然语言回退），前端不再维护副本，任何路径不暴露原始场景 id

### 4.11 历史记录

- 历史三端点仅对认证用户开放（访客无历史）
- 会话列表与消息回放均游标分页（limit 1–100，默认 20）；列表游标带 HMAC 签名防篡改
- 查看历史会话、对应场景 / 角色 / 消息 / 反馈与复盘

## 5. 系统模块划分

后端采用“产品结构清晰 + Agent 内部模块化”的混合结构。

### 5.1 API 层

- `auth`：注册 / 登录 / 刷新 / 当前用户 / 邮箱验证 / 密码重置 / 登出
- `media`：上传、元数据、签名读 URL、场景分析状态
- `sessions`：会话创建、状态、回复（整包 / 流式）、复盘、语音引导与收口
- `history`：会话列表、详情、消息回放（游标分页）
- `deepgram`：语音 Agent 思考模型代理

### 5.2 Agent / Engine 模块

#### `scene_engine`

- 负责图片理解和场景推断：图片质检、视觉模型调用（主备双通道）、输出场景 / 角色 / 开场白 / 视觉锚点 / 教学词汇候选 / 置信度
- 缓存读写与提示词版本管理在此层

#### `coach_engine`

- 负责生成对话回复：角色一致性、多轮推进、整包与流式两种输出形态
- 消费学员档案注入块与 CEFR 估计

#### `feedback_engine`

- 负责生成学习反馈：纠错、自然表达、关键词汇；输出 9 类错误归类与 CEFR 观测（档案更新的数据源）

#### `session_engine`

- 会话编排：串联前三个 engine，管理会话生命周期
- 职责扩展至：流式事件编排、语音引导 / 收口编排、LLM 复盘增强分支、学员档案滚动更新、历史分页游标编解码、场景展示文案下发

## 6. 目录结构与职责说明

### 6.1 顶层目录

```text
EchoWhale/
├── api/               # FastAPI 后端
├── frontend/          # React 前端
├── docs/              # 产品、协议、部署与治理文档
├── tests/             # 测试代码
├── infra/             # 部署与基础设施配置
├── tools/             # 仓库治理工具（agent_ops 等）
└── README.md          # 项目说明
```

- `api/`：后端主目录——API、业务编排、Agent 模块、数据模型、第三方服务接入
- `frontend/`：Web 前端——上传、对话、反馈、历史、语音练习界面
- `docs/`：PRD、API 文档、部署 runbook、版本进度与控制面
- `tests/`：API、模块级、集成测试
- `infra/`：Docker、Cloudflare、Terraform 等部署配置

### 6.2 后端目录结构

```text
api/
├── main.py            # FastAPI 启动入口（中间件、异常处理器、健康端点）
├── core/              # 配置与安全（Settings、生产门控、签名 / JWT）
├── common/            # 公共组件（统一信封、异常、依赖注入、中间件、request id）
├── contracts/         # API 请求 / 响应契约
├── routes/v1/         # API 路由层（auth / media / sessions / history / deepgram）
├── services/          # 应用服务层（媒体、认证、限流等）
├── modules/           # Agent / Engine 模块层
├── models/            # 域模型（Pydantic）
├── db/                # 持久化层（SQLAlchemy 异步仓储）
├── integrations/      # 第三方接入（LLM、R2、Deepgram、Redis）
├── tasks/             # RQ 异步任务与 worker
└── migrations/        # Alembic 数据库迁移
```

职责要点（与早期版本的差异）：

- `db/`：PostgreSQL 持久化层，SQLAlchemy 异步仓储实现；不再使用内存存储
- `tasks/`：已承载 RQ 消费——`auth-mail`（注册 / 重置邮件）与 `scene-analysis`（异步图片分析）两个队列，含 worker 入口
- `migrations/`：Alembic 迁移目录，13 个版本已落地（媒体、会话、认证、运行时、缓存、档案等表）
- `common/`：统一响应信封、公共异常体系、访客 / 认证依赖、请求体大小门、request id 基建

### 6.3 Agent 模块目录结构

```text
api/modules/
├── scene_engine/
├── coach_engine/
├── feedback_engine/
└── session_engine/
```

每个 engine 内部保持一致结构：`agent.py`（主逻辑）、`schema.py`（输入输出结构）、`service.py`（对外入口）、`prompts/`（提示词），scene_engine 另有 `providers/`（视觉模型适配）与 `tools/`。

`session_engine/` 额外承载编排层能力：

- `agent.py`：会话主编排（回复轮、流式事件、语音引导 / 收口、历史分页）
- `review_builder.py`：复盘组装与场景展示文案单一事实源（SCENE_COPY）
- `review_summarizer.py`：LLM 复盘增强分支
- `learner_profile.py`：档案更新数学与提示词注入渲染（纯函数）
- `sample_presets.py`：示例场景预设

## 7. 技术方案

### 7.1 前端

- React 19 + Vite + TypeScript + Tailwind CSS
- 页面结构：首页上传 / 会话练习（含流式反馈与语音入口）/ 复盘 / 历史
- 前端质量门禁：Vitest + Testing Library，覆盖率四阈值（statements / branches / functions / lines）

### 7.2 后端

- FastAPI，按 `routes / services / modules / contracts / db / integrations` 分层
- 统一响应信封 `ApiResponse{code, message, data}` 与业务错误码体系（详见 [api.md](api.md)）
- 全局限流（owner 键 + 匿名 IP 兜底键）、请求体大小门、request id 贯穿日志

### 7.3 存储与基础设施

- 数据库：PostgreSQL + SQLAlchemy（异步）+ Alembic 迁移；用户、会话、消息、复盘、媒体、认证、运行时事实、场景缓存、学员档案等全部持久化
- 队列：Redis + RQ，两个队列——`auth-mail`（注册 / 重置邮件）与 `scene-analysis`（异步图片分析）；Redis 缺席时限流降级进程内、邮件入队显式报错
- 对象存储：Cloudflare R2（S3 兼容），签名读 URL
- 部署：Docker 镜像（uv --frozen），compose 参考编排 postgres + redis + api + worker，见 [deployment.md](deployment.md)

### 7.4 模型策略

- `MODEL_RUNTIME_MODE` 双运行时：`mock`（本地开发与测试，零外部依赖，LLM 调用返回预设数据、复盘短路）/ `live`（真实调用，生产门禁强制 live）
- 每类引擎独立主备双通道：`VISION_PRIMARY_*` / `VISION_FALLBACK_*`、`TEXT_PRIMARY_*` / `TEXT_FALLBACK_*`
- 单次调用输出 token 硬顶 + 教练输出字符硬顶，成本上界可控
- 保留 provider 抽象，不将模型供应商细节暴露到业务层

### 7.5 身份与安全

- 认证：JWT 访问令牌 + 刷新 Cookie + 邮箱验证码（冷却 60 秒 / 每日 5 封 / 验证码 5 次尝试）+ 密码重置
- 匿名访客：HMAC 签名 Cookie（`echowhale_visitor_id`），验签失败静默重签，客户端无法伪造身份
- 资源归属：owner 串（`user:` / `visitor:` 前缀）贯穿存储与限流键；越权访问一律收敛 404
- 生产启动门控：环境白名单之外的取值强制校验 17 项清单（密钥、数据库、Redis、R2、SMTP、语音等），缺一即拒绝启动

### 7.6 实时语音

- Deepgram Agent：后端签发受限会话令牌（TTL 600 秒），前端直连语音 WebSocket
- 思考模型经后端代理（模型白名单 + 会话维度限流 + SSE 透传），密钥不出网
- 收口路径负责转写去重、反馈、复盘与语音事实落库

## 8. Cloudflare 方案

### 8.1 使用范围

- Cloudflare R2：图片存储（已接入，上传直传 + 签名读 URL）
- Cloudflare Pages：前端部署
- Cloudflare CDN：静态资源与图片分发

### 8.2 设计原则

- Cloudflare 负责分发和媒体链路
- 模型推理仍由后端或外部模型 API 承担
- 复杂推理不迁移到边缘侧

## 9. 开源与简历导向要求

### 9.1 开源要求

- 仓库结构清晰，访客一眼能看懂产品入口
- 提供 `.env.example`、README、PRD、API 文档（[api.md](api.md)）与部署 runbook（[deployment.md](deployment.md)）——均已具备
- 模块边界清楚，便于后续贡献

### 9.2 简历亮点

- FastAPI 模块化后端设计与统一协议层（信封 / 错误码 / 限流 / SSE）
- React 前端交互设计（流式渲染、语音练习）
- 基于场景的 Agent 编排（并发分支、增强分支降级、失败语义分层）
- 学员档案：LLM 输出 → 结构化画像 → 提示词注入的闭环
- 第三方模型与存储的适配层设计（主备双通道、mock/live 双运行时）
- Cloudflare 基础设施整合能力（R2 直传、Pages、CDN）

## 10. 验收标准

### 10.1 功能验收

- 完整链路：上传图片（或示例场景）→ 创建会话（含 202 异步分析分支）→ 流式多轮对话 → 查看复盘 → 查看历史
- 语音练习：bootstrap 签发令牌 → 实时对话（think 代理）→ complete 收口产生反馈与复盘
- 学员档案：认证用户多轮练习后，错误画像 / CEFR 估计 / 场景频次随轮滚动更新，且注入后续轮次的教练与反馈提示词
- LLM 复盘：每轮随响应下发复盘文案；live 失败或 mock 模式下降级为模板复盘，主流程不受影响
- 场景文案下发：会话与历史响应携带 `scene_title` / `role_label`，前端不暴露原始场景 id
- 系统对不同图片文件名或场景输入能给出不同会话结果；每轮都能输出结构化反馈

### 10.2 工程验收

- 后端门禁：`uv run pytest tests --cov=api` 全绿（当前基线 540 passed / 9 skipped），覆盖率 ≥ 87（pyproject `fail_under`）
- 代码风格：`uv run ruff check api tests tools` 与 `uv run black --check api tests tools` 全绿
- 前端门禁：`npm run typecheck` 通过；覆盖率四阈值 statements 76 / branches 74 / functions 78 / lines 76
- 生产门控：`Settings.validate_runtime()` 强制生产清单，缺项拒绝启动
- 控制面：`docs/control/` 索引与 agent_ops 校验保持一致
- PRD 与代码零矛盾：新协作者按 PRD 理解的当前形态与实现一致

## 11. 版本规划

> 本节是历史版本记录与阶段意图，不是 changelog。逐批次进度记录见
> [docs/versions/](versions/README.md) 与 docs/features/ 各 feature 文档；批次状态由
> docs/control 控制面承载。

### v0.1（已完成）

- 仓库基础结构、PRD、README、架构文档

### v0.2（已完成）

- mock 数据链路；图片上传、会话创建、消息发送打通

### v0.3（已完成）

- 接入真实模型与 Cloudflare R2；前端基础交互页面
- MVP 目标达成（见 §2.1）

### v0.4（已完成）

- 会话总结与历史复习能力（实际由 LLM 复盘承载，见 docs/features/teaching_kernel_prompts）
- 测试与部署文档完善

> v0.4 之后陆续交付（均以 docs/versions/ 批次记录为准）：认证体系（JWT + 邮箱验证）、
> Deepgram 实时语音 Agent、SSE 流式回复、场景分析缓存与异步化、学员档案与提示词注入、
> LLM 复盘、场景文案服务端下发、统一限流与请求体门禁、/readyz 与 request id 基建。
> 这些能力已并入 §1–§10 的当前形态描述。

### v0.5（阶段意图）

本版本完成文档与协议层收口：PRD 按“产品现在是什么”重写（本文档），新增对外协议文档
[api.md](api.md)（统一信封、错误码、限流、SSE、202 轮询、身份、游标分页、请求体上限、
健康端点）。

下一阶段候选方向（仅意图，不含时间表，逐项独立立项）：

1. **档案读取 API 与前端进度页**（已交付 2026-10-06：`GET /api/v1/learners/me/profile` + `/progress` 页，能力并入 §4.8，见 docs/features/learner_profile_progress）
2. **LLM ReviewCopy 生产消费扩展**：复盘 LLM 产出的部分字段（如 scene_title / role_label）尚未被复盘卡片消费，评估接入与硬顶
3. **评测驱动提示词修正**（已交付 2026-10-06：coach/review live 评测首跑、4 项已记录
   疑似问题 + 3 项 live 新发现逐项分诊处置（meta 黑名单收窄 + 提示词接地行、follow_up
   区间、ReviewCopy 五字段截断 cap、mock 复读路径修复、judge 兜底、REVIEW_PROMPT 短例句
   子句），复跑达标，见 docs/features/eval_prompt_fixes）
4. **可观测性（OTel / Langfuse）**（OTel 三层 span 已交付，见 docs/features/otel_engine_spans 与 [observability.md](observability.md)；Langfuse 对接为用户侧配置）：在现有 request id 与结构化日志基础上接入链路追踪与 LLM 调用观测
