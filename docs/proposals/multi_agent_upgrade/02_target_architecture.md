# 架构选型对比与多 Agent 目标架构设计（多 Agent 升级 · 任务 2+3）

> 检索日期：2026-10-28。所有外部事实标注信息日期与来源；供应商自述材料（如 Deepgram 官方对比文）
> 已标注「vendor 自述」，采信其事实性内容、折扣其倾向性结论。
> 上游文档：[01_gap_analysis.md](01_gap_analysis.md)（差距清单 G1–G9）。

## 1. 调研事实基线（先调研，再设计）

| 事实 | 信息日期 | 来源 |
| --- | --- | --- |
| OpenAI Realtime API 语音链路 gpt-realtime GA（speech-to-speech，5 个可引导音色，prompt caching 降价） | 2025-08 | OpenAI 发布（Reddit r/singularity 转载，2025-08） |
| gpt-realtime-2 音频 token 定价 $32/$64 per 1M（in/out），文本 $4/$24 | 2026-10 | wiro.ai 模型页（第三方聚合） |
| OpenAI Realtime 会话上限 60 分钟；VAD 提供 server VAD 与 semantic VAD（eagerness 可调） | 2026-07 | OpenAI 文档（经 Deepgram 对比文引用） |
| Deepgram Voice Agent API GA；单 WebSocket 承载 listen/think/speak，内建 barge-in 与 turn-taking（Flux）；支持 mid-conversation prompt 更新、BYO LLM（think.endpoint） | 2025-06 GA / 2026-07 更新 | Deepgram 产品页与 Flux 文档（vendor 自述） |
| Deepgram Growth 档 $0.0500/min 连接计价（与 prompt 长度无关）；默认并发 2026 年初扩至 45+；文档化 429 失败语义 | 2026-07 | Deepgram 官方对比文（vendor 自述） |
| LangGraph（图状态机 + checkpointing）、CrewAI（角色制）、OpenAI Agents SDK（轻量 handoff）、PydanticAI（类型安全）四派并存的格局未变；LangGraph 生产就绪度评价最高 | 2026-05 | Galileo / Speakeasy / GuruSup 三份框架对比 |
| PydanticAI 开发体验评分 8/10（五框架基准第一），但生态规模约为 LangChain 的 1/15 | 2026 | Speakeasy 引 Nextbuild 90 天基准 |
| MCP：月 SDK 下载 97M、server 5,800+；2026-07-28 规范发布转向 stateless / fully remote | 2026-10 / 2026-08 | digitalapplied 统计、Gravitee 规范解读 |
| 记忆层三强：Mem0（事实提取）、Zep（时序知识图）、Letta（agent memory OS）；LoCoMo / LongMemEval（ICLR 2025）为主流基准；Mem0 付费档 $19/$249 月，Zep $125/$375 月 | 2026-03 ~ 2026-09 | 多份对比文 |
| Langfuse 原生消费 OTLP（GenAI 语义约定），无需专用 SDK | 2025-11 ~ 2026-02 | Langfuse 官方集成页 |
| Azure Pronunciation Assessment：语音学习场景成熟方案（音素级评估），Speech SDK/REST 提供 | 2025-11 | Microsoft Learn 官方文档 |
| STT 延迟基准：Deepgram Nova-3 中位 TTFT 992ms（Coval 榜基线） | 2026-05 | gradium.ai STT 基准 |

## 2. 选型对比表

### 2.1 编排框架

| 候选 | 优势 | 劣势 | 与本项目的适配判断 | 结论 |
| --- | --- | --- | --- | --- |
| LangGraph | 图状态机 + checkpointing + 时间回放，生产就绪度公认最高；与 Langfuse span 生态顺滑 | 重运行时抽象；学习曲线陡；状态即 TypedDict 的范式与现有 FastAPI 分层是两套心智 | 本项目一轮对话是**确定性管道 + 固定并发分支**（feedback ∥ coach → review），没有动态路由、循环或人工审批节点——用不上图运行时的核心价值；引入它意味着重写 `session_engine/agent.py` 全部编排与 540 个测试的语义锚点，违反「禁止推倒重来」硬约束 | **淘汰**。若未来出现「课程规划师需要多轮自主规划」的真实需求，可在 curriculum_engine 内局部使用，不做全仓编排底座 |
| OpenAI Agents SDK | 轻量、handoff 语义干净、内建 tracing/guardrails | hosted tools 仅 OpenAI 模型可用；handoff 是「转交」模型，与本项目「多角色并行分支 + 各自独立降级」的形态不匹配；加深单一 vendor 绑定 | 现有 `TEXT_PRIMARY/FALLBACK` 双通道抽象是供应商无关的核心设计；Agents SDK 的 runner 会绕开它。语音 think 模型经自建代理，模型白名单已在后端控制 | **淘汰** |
| CrewAI | 角色制 DSL 原型最快（~20 行起 crew） | 粗粒度错误处理、无 checkpointing；角色/目标/backstory 抽象与现有 prompts/ 体系重叠 | 本项目的「角色」是教学角色（barista/teammate），不是 CrewAI 的 agent 角色——两套角色概念会打架；错误语义分层（failed/degraded）是本项目最强的工程资产，CrewAI 表达不了 | **淘汰** |
| PydanticAI | 类型安全 + 结构化输出，与仓库 Pydantic 契约风格同源；开发体验基准最高 | 生态小 15 倍；multi-agent 需经 tools/graph 自拼；引库仍是外部依赖 | 方向最对味（engine 之间传 Pydantic schema 正是现状），但现状已经零成本拥有同样性质：`agent.py + schema.py` 就是手写版 PydanticAI | **备选保留**。P0 以自研轻量协作层实现同等性质；若 P2 curriculum 需要工具循环，可局部引入 |
| **自研轻量协作层**（采用） | 显式 Agent 协议（Protocol + Pydantic 消息 schema）+ 注册表；编排器只依赖协议；现有 failure policy / OTel span / mock-live 双运行时零改动继承；540 测试全量保留为回归网 | 协议设计自己负责（约 300–500 行）；没有现成社区 | 与「渐进迁移」硬约束完全对齐：engine 四件套结构不动，只把「agent 怎么被调用」从硬编码 gather 升级为显式协作层（对应 G1/G6） | **P0 采用** |

> 判断依据（Anthropic《Building effective agents》，2024-12）：能被 prompt chaining / parallelization
> 表达的流程不要上 graph 运行时。本项目一轮对话正是 chaining + 并行化；目标架构新增的 agent
> （发音/课程/记忆）也各自是**增强分支**，不改变主链路的确定性——这是选型的根本理由。

### 2.2 实时语音方案（级联 vs 端到端）

| 候选 | 优势 | 劣势 | 与本项目的适配判断 | 结论 |
| --- | --- | --- | --- | --- |
| Deepgram Voice Agent（级联：Flux listen + BYO think + Aura-2 speak，现状） | 已深度接入（bootstrap/令牌代数绑定/think 代理/收口去重全链路在仓）；barge-in 与 turn-taking 内建（Flux 专为此调优）；连接计价 $0.05/min 与 prompt 长度无关，成本可预测；pipeline 各段可观测可调参；BYO think 正是后端 agent 的天然接入点；支持 mid-conversation prompt 更新 | STT 锁定 Deepgram 栈（vendor 自述）；级联总延迟 = EOT + LLM TTFT + TTS 首包，理论上限高于端到端 | 主提示词基线明确「Deepgram 已深度接入」；语音会话生命周期治理（代数令牌、审计 F12）是近期刚收口的资产，替换即归零 | **保留为主线** |
| OpenAI Realtime（端到端 speech-to-speech） | 会话内统一模型，情感/语气连贯性最佳；无需自管级联延迟 | token 计价随 prompt/上下文增长（gpt-realtime-2 音频 $32/$64 per 1M，2026-10），长会话成本不可预测；60min 会话上限；中间态不可观测——与本项目「可观测性」资产方向相反；接入意味着整条语音链路重写 | 教育陪练是低并发、体验敏感场景，端到端是合法备选；但成本模型（每会话分钟数不可控）与可观测性劣势都打在痛点上 | **P2 备选路线**：先在文本链路验证多 agent 价值，语音换端到端仅当级联延迟实测不可接受时立项 |
| Gemini Live API | 多模态能力强、Google 生态 | 同样是黑盒会话模型；与现有 AWS/R2/FastAPI 栈无协同 | 引入第二家语音 vendor 无现实验证需求 | **淘汰** |

### 2.3 记忆方案

| 候选 | 优势 | 劣势 | 与本项目的适配判断 | 结论 |
| --- | --- | --- | --- | --- |
| Mem0（OSS/托管） | 事实提取式记忆开箱即用；LoCoMo 91.6（vendor 自述，2026-09） | 托管 $19/月起；引入新存储与新延迟面；「记忆什么」需要教育域定义 | 学习者的「记忆」是结构化教育事实（掌握句型、卡壳语法点），不是开放对话事实——9 类错误封闭集合 + CEFR 的写侧防御哲学应当延续 | **P2 再评估** |
| Zep | 时序知识图，时间推理强 | 托管 $125/月起；图谱运维复杂度对单人项目不成比例 | 同上，且成本档位最高 | **淘汰** |
| Letta | agent 状态即记忆，自管友好 | 引入整套 agent runtime，与自研编排层冲突 | 等于把编排权交给 Letta | **淘汰** |
| **自研记忆事件表**（采用） | 延续现有档案设计：纯函数更新、写侧封顶、注入面有界；一张 `memory_events` 表（掌握/卡壳/复习事件）+ Memory Manager 渲染注入块；零新外部依赖 | 语义提取靠规则 + 现有 feedback 错误归类，深度不及 Mem0 | G4 缺口的最小充分解：先有「事件化长期记忆」这一层，深度语义化留给 P2 按数据量决定 | **P1–P2 采用** |

### 2.4 工具协议（MCP）

| 判断项 | 内容 |
| --- | --- |
| 现状 | 进程内 agent 协作，工具即 Python 函数（`scene_engine/tools/` 等） |
| MCP 现状（2026-10） | 月 SDK 下载 97M、server 5,800+，事实标准；2026-07-28 规范转向 stateless/remote |
| 适配判断 | 本项目 agent 全部同进程，跨进程工具协议是纯开销；但「把 EchoWhale 的教学能力（场景库、档案、发音评估）暴露为 MCP server」是低成本的外部生态故事——别人的 agent 可以调用 EchoWhale 练口语 |
| 结论 | **不做运行时依赖**；P2 可选交付一个只读 MCP server（learner profile + scene presets），作为简历亮点而非架构组件 |

### 2.5 评测与可观测

| 候选/方案 | 优势 | 劣势 | 结论 |
| --- | --- | --- | --- |
| Langfuse（消费 OTLP） | 原生吃现有 OTel 三层 span，零代码迁移；LLM 观测（prompt/completion/评测）一体化 | 自托管部署或云付费 | **P1 接入**（PRD v0.5 已列「用户侧配置」） |
| 现有自建评测台扩展 | coach/scene/session 三台已有硬规则 + judge 形态 | feedback/发音/课程无评测（G8） | **P0–P2 按期补齐**：feedback 评测台（P0）、发音硬规则（P1）、curriculum judge（P2） |
| Azure Pronunciation Assessment | 音素级评估成熟、语言学习场景官方支持（2025-11 文档） | 新 vendor 依赖；定价待补（见 §6） | **P1 采用**为 pronunciation_engine 的 live provider，mock provider 本地实现，遵守 mock/live 双运行时纪律 |

## 3. 目标架构设计（任务 3）

### 3.1 Agent 角色清单

| Agent | 职责 | 输入 → 输出 | 模型档次 | 失败语义（降级到哪、用户看到什么） |
| --- | --- | --- | --- | --- |
| **Orchestrator**（编排者，非 LLM） | 会话内事件路由与阶段决策：文本轮 / 语音轮 / 收口 / 历史读；决定哪些增强分支起飞 | 用户事件 + 会话头 → 各 agent 调用计划与 SSE 事件序 | 无模型（纯代码状态机） | 编排器 bug 即整轮失败（与现状同：教练分支失败整轮上抛，不落库） |
| **Conversation Coach** 对话教练 | 角色化英文回复，i+1 难度，流式 | 场景 + 角色 + 8 轮窗口 + 记忆注入块 → 流式文本 | 大模型精算（TEXT_PRIMARY 流式，300 token 预算） | 整轮失败不落库，用户看到错误卡片重试（现状保持） |
| **Feedback Coach** 反馈教练 | Grammar / More Natural / Useful Words + 9 类错误归类 + CEFR 观测 | 学习者消息 + 场景 + 记忆注入块 → 结构化 JSON | 中档模型高频（JSON mode，400 token 预算） | 降级占位反馈（「本轮反馈生成失败，下一轮照常」），本轮照常返回落库（现状保持） |
| **Pronunciation Coach** 发音教练（新增） | 音素级发音评估 + top 问题音 + 教学建议 | 语音轮音频段 + 对齐转写 → 发音分数与诊断（mock/live 双 provider） | 专用 API（Azure PAS）+ 小模型只做中文诊断文案 | 评估失败 → 本轮无发音分区（UI 隐藏），文字反馈与转写不受影响；诊断文案失败 → 只给分数不给文案 |
| **Curriculum Planner** 课程规划师（新增） | 读档案 + 记忆事件，产出「下一步练什么」：场景 / 目标语法点 / 复习建议 | 档案 + memory_events + 场景库 → 下一步建议 JSON | 中档模型，超低频（每会话开始/收口各 1 次，≈2 次/会话） | 建议缺席 → 前端维持自由选场景（现状行为），绝不阻塞练习 |
| **Memory Manager** 记忆管理员（新增） | 把单轮结果事件化为长期记忆（掌握/卡壳/复习），渲染跨会话注入块 | FeedbackResult + 会话上下文 → memory_events 行 + 注入块 | 非 LLM（规则提取，复用 9 类封闭集合）；可选小模型摘要 | 写失败 → 记日志降级（与现档案更新同款增强分支）；读失败 → 回退现有档案注入 |
| **Review Summarizer** 复盘 | 单轮中文复盘文案 | 反馈 JSON + 消息 → ReviewCopy | 小模型高频（300 token 预算，5s 有界） | mock 短路 / 超时降级模板复盘（现状保持） |

### 3.2 协作链路图（一轮语音对话从进入到反馈落库）

```mermaid
sequenceDiagram
    autonumber
    participant U as 用户(浏览器)
    participant DG as Deepgram Voice Agent(WS 直连)
    participant OR as Orchestrator<br/>(后端, 非LLM)
    participant MM as Memory Manager
    participant CP as Curriculum Planner
    participant CC as Conversation Coach<br/>(经think代理)
    participant PC as Pronunciation Coach
    participant FB as Feedback Coach
    participant RV as Review Summarizer

    rect rgb(235, 244, 255)
    Note over U,CP: 会话启动阶段(bootstrap)
    U->>OR: POST /voice/bootstrap
    OR->>MM: 读档案+记忆注入块 [同步, PK点查, 失败→None降级]
    OR->>CP: 产出本轮练习目标 [异步fire-and-forget, 失败→无建议]
    OR-->>U: 令牌(TTL600s)+agent_settings(think=自建代理+代数令牌)
    U->>DG: 建立 WebSocket
    end

    rect rgb(240, 255, 240)
    Note over U,RV: 一轮语音对话(barge-in 由 Flux 在 DG 内部处理)
    U->>DG: 音频流
    DG->>DG: Flux EOT/turn-taking; 用户打断→取消think请求
    DG->>OR: think请求(SSE, 同步, 会话维度限流120/5min)
    OR->>CC: 注入记忆块后生成回复 [流式]
    CC-->>OR: delta*
    OR-->>DG: SSE透传; 打断即断流(不落库半条回复)
    DG-->>U: Aura-2 合成音频(可再次打断)
    par 逐轮增强分支(异步, 不阻塞对话, 各自独立降级)
        OR->>PC: 本轮音频段+转写 → 音素分数 [失败→本轮无发音分区]
        OR->>FB: 转写文本 → 结构化反馈 [失败→占位反馈]
        OR->>MM: 写memory事件(掌握/卡壳) [失败→记日志]
    and
        OR->>RV: 反馈JSON → 中文复盘 [5s有界, 失败→模板复盘]
    end
    end

    rect rgb(255, 248, 235)
    Note over U,CP: 收口阶段(voice/complete)
    U->>OR: POST /voice/complete(transcript+client诊断)
    OR->>OR: 尾段转写去重(tail-overlap)
    OR->>FB: 最后一条学习者发言 → 反馈 [失败→占位]
    OR->>RV: 复盘 [失败→模板]
    OR->>OR: 原子落库: 消息+review+voice_fact(代数不变)+事件
    OR->>MM: 收口记忆事件批量写入 [异步]
    OR->>CP: 更新下一步建议 [异步]
    OR-->>U: session+review(含发音分区,若P1已上线)
    end
```

**同步/异步边界**：同步面只有「对话主链路」（DG think ↔ Orchestrator ↔ Conversation Coach，SSE）与
bootstrap 的档案点查；发音/反馈/记忆/复盘/课程全部是增强分支——与现有 failure policy 同构，
任何增强分支失败都不改变事件序与落库行为。

**barge-in 处理**：打断在 Deepgram 层（Flux）发生并取消 in-flight think 请求；Orchestrator
把该轮标记为 interrupted、丢弃半条 coach 回复、不落库——语义与现有文本流断连路径一致
（`stream_reply` 的 `finally` 取消逻辑）。

**最慢的一步**：语音轮是 think 模型 TTFT（级联链路 1–2s 量级，见 §6）；文本轮是 coach 首 token
（P95 由主模型决定）。发音评估为音频收口后异步，不在用户等待路径上。

### 3.3 迁移映射（禁止推倒重来）

| 目标组件 | 对应现有代码 | 处置 |
| --- | --- | --- |
| Orchestrator | `api/modules/session_engine/agent.py`（990 行） | **拆分保留**：reply/stream_reply/voice 编排水务迁入 `orchestration/`；`inspect.signature` 兼容分派技术债（agent-governance 二期清单）顺带清除；agent 调用改经协作层协议 |
| Agent 协作协议（新增） | 无 | **新增** `api/modules/orchestration/protocol.py`：`Agent` Protocol + Pydantic 消息 schema + 注册表 + 三值终态（ok/degraded/failed）类型化 |
| Conversation Coach | `api/modules/coach_engine/*` 四件套 | **原样保留**，按协议包一层注册 |
| Feedback Coach | `api/modules/feedback_engine/*` | **保留 + 补评测台**（G8）：新增 `feedback_engine/evaluation.py`（对齐 coach 三台形态） |
| Pronunciation Coach | 无 | **新增** `api/modules/pronunciation_engine/`（agent/schema/service/prompts + providers/azure_pas.py + mock）——engine 四件套结构照搬 |
| Curriculum Planner | `sample_presets.py`（场景库雏形） | **新增** `api/modules/curriculum_engine/`；sample_presets 升级为场景库数据源 |
| Memory Manager | `api/modules/session_engine/learner_profile.py`（纯函数） + `api/db/learner_profile_db.py` | **扩展保留**：新增 `memory_events` 表迁移 + 事件化更新纯函数；注入渲染函数原地扩展 |
| Review Summarizer | `api/modules/session_engine/review_summarizer.py` | **原样保留** |
| 语音链路 | `api/integrations/deepgram/voice_agent.py` + think 代理路由 | **原样保留**；think 代理成为语音侧 Conversation Coach 的天然入口，发音/反馈逐轮分支挂在收口与 think 旁路 |
| 评测台 | `api/modules/{coach,scene}/evaluation.py`、`session_engine/evaluation.py` | **保留 + 扩展**：新增 feedback/pronunciation/curriculum 评测台；live 评测门控沿用 RUN_COACH_EVAL 模式 |
| 可观测 | `api/common/telemetry.py` 三层 span | **扩展**：engine span 目录新增 pronunciation/curriculum/memory，三值终态语义不变 |

### 3.4 分期路线（每期一组用户故事 + 工程验收标准）

#### P0 · 协作协议与编排重构（零新增模型调用，纯结构升级）

**用户故事**
- 作为开发者，我能实现 `Agent` 协议并在注册表注册一个新 agent，全程不改 Orchestrator 主干。
- 作为面试官，我读 `orchestration/` 能在 10 分钟内看懂谁调用谁、失败时谁降级到哪。

**工程验收标准**
1. `session_engine/agent.py` 拆出 `orchestration/`（协议 + 注册表 + 编排器），agent.py 保留门面转发，行数减半。
2. 现有 540 测试零语义变更全绿（文本/流式/语音/历史各路径响应逐字节兼容）；新增协作层单测 ≥15 条。
3. OTel span 树与三值终态语义不变（`docs/observability.md` 表格不破）。
4. feedback_engine 补齐评测台（G8），硬规则五维 + live 门控，README 记录首跑结果。
5. 门禁全绿：pytest 覆盖率 ≥87、ruff、black、前端四阈值、`agent_ops check`。

#### P1 · 发音教练 + 语音逐轮反馈（首个新 agent，第一块差异化）

**用户故事**
- 作为学员，我在语音练习中每说完一轮，能看到本轮发音分数与最需要改的问题音（延迟纠错：不打断对话流）。
- 作为学员，收口复盘页出现「发音」分区：分数、问题音、一句中文建议。

**工程验收标准**
1. `pronunciation_engine` 四件套 + `providers/azure_pas.py`（live）/ mock provider（默认），遵守 mock/live 双运行时与生产门控清单（新增 17+N 项校验）。
2. 语音收口契约向后兼容扩展（发音分区可选字段，旧客户端零破坏）；语音会话内逐轮评估走异步增强分支，think 链路 P95 延迟无可测退化（span 数据对比）。
3. 发音评测台：硬规则（分数区间、问题音 ⊆ 音素集）+ judge（诊断文案可用性）；mock 全链路测试覆盖降级语义（评估失败 → UI 隐藏分区）。
4. OTel 新增 `engine.pronunciation` span（degraded 语义）；llm_usage 账本新增 pronunciation 维度。
5. PRD §2.3 「发音打分 non-goal」同步修订，api.md 契约更新（治理要求：PRD 与代码零矛盾）。

#### P2 · 记忆管理员 + 课程规划师（学习产品闭环）

**用户故事**
- 作为学员，连续多日练习后，首页出现「上次你在咖啡店场景卡在虚拟语气，今天再来一次？」的推荐。
- 作为学员，/progress 页显示成长轨迹：掌握事件、卡壳事件、复习完成率。

**工程验收标准**
1. `memory_events` 迁移（掌握/卡壳/复习三类事件，写侧封顶）；Memory Manager 纯函数 + 注入渲染有界。
2. `curriculum_engine` 上线：会话开始/收口各 1 次调用（成本护栏写进 settings），建议缺席不阻塞任何主链路。
3. curriculum 评测台含 judge（建议与档案一致性）；Langfuse 接入消费现有 OTLP span（观测三 agent 协作链路）。
4. /progress 页扩展（前端门禁四阈值保持）；api.md 新端点契约。
5. （可选亮点）只读 MCP server：暴露 learner profile + 场景库。

### 3.5 成本与延迟估算（量级）

**文本单轮成本**（假设 coach 输入 ≈1.5k tokens（系统提示词 + 8 轮窗口 + 注入块）、输出 ≈200；
feedback ≈1k in / 200 out；review ≈0.8k in / 150 out）：

| 定价锚点（标注日期） | 单轮估算 |
| --- | --- |
| gpt-4o-mini：$0.15/M in、$0.60/M out（2024-07 定价，长期未变） | (3.3k×$0.15 + 0.55k×$0.60)/1M ≈ **$0.0008/轮** |
| gpt-4.1-mini：$0.40/M in、$1.60/M out（2025-04 定价） | (3.3k×$0.40 + 0.55k×$1.60)/1M ≈ **$0.0022/轮** |

量级结论：**文本单轮 $0.001–0.002（约 0.007–0.016 元），每千轮 $1–2**。P2 新增 curriculum
（2 次/会话 ≈ 4k in/200 out）约 +40% 文本成本；控制手段已有：token 硬顶（300–500）、模型分级、
场景缓存。**待补：真实分布的输入 token 均值——测法：llm_usage 账本按 `llm.usage.prompt_tokens`
聚合 P50/P95（OTel attempt span 已在采集）。**

**语音会话成本**（10 分钟会话）：
- Deepgram Voice Agent（Growth $0.05/min，2026-07 vendor 自述）：$0.50
- think 调用 ≈ 10 轮 × 文本单轮 coach 成本 ≈ $0.01
- 合计 ≈ **$0.51/会话（约 3.7 元）**。发音评估（P1，Azure PAS）：**待补：Azure Speech 定价页核价——
  测法：收口前语音轮音频时长累计 × 单价，与 Deepgram 分钟数同源可测。**

**端到端延迟预算（语音级联一轮）**：

| 段 | 量级 | 依据 |
| --- | --- | --- |
| EOT 检测（Flux eager 阈值 0.4，`config.py:152`） | 数百 ms | 现仓配置，实测待补（G7：延迟测量是 P0 顺带交付） |
| think LLM TTFT | 300–900ms | 主流 OpenAI 兼容 API 量级；STT 参考基线 Nova-3 TTFT 中位 992ms（2026-05 基准） |
| Aura-2 TTS 首包 | 100–300ms | vendor 量级，实测待补 |
| **合计** | **≈1–2s**，会话式体验合格线内 | 需以实测数据替换（P0 验收项） |

文本轮：feedback ∥ coach 并发（现状），首反馈卡 < coach 首 token；P95 由主模型 TTFT + 网络决定，
现仓 `llm_request_deadline_seconds=45` 为硬上限，体验目标 2–4s 首响。

## 4. 面试官拷问预答（本节对应验收标准）

- **「为什么不用 LangGraph？」**——一轮对话是确定性管道 + 并行分支，不是需要 checkpointing 的动态图；
  引入图运行时要重写编排层与全部测试语义锚点，收益为零。Anthropic 官方工程指南（2024-12）同样建议
  简单 pattern 优先。
- **「多 agent 到底多了什么？」**——三个新能力：显式 Agent 协议（谁都能被替换/降级/观测）、
  发音维度（新增模态）、记忆事件层（跨会话连续性）。不是「多个 prompt」。
- **「每个 agent 失败时用户看到什么？」**——教练失败整轮重试、反馈失败占位卡、复盘失败模板文案、
  发音失败隐藏分区、课程建议缺席保持自由选择、记忆失败回退静态注入。六条全部有测试锁定。
- **「数据从哪来、到哪去？」**——图见 §3.2；写入面：消息/review/voice_fact/事件/memory_events/llm_usage；
  读取面：教练/反馈/语音 think/课程规划。
