# STAR 项目介绍（多 Agent 升级 · 任务 4）

> 双版本 × 中英双语。版本 A 今天可贴简历（只含已实现能力）；版本 B 是多 Agent 改造完成后的形态，
> 逐条标注「需先完成任务 3 的哪一期才可写上简历」（见 [02_target_architecture.md](02_target_architecture.md) §3.4）。
> 诚实性纪律：所有数字可溯源；未实现的能力与未测的数字绝不进入版本 A。

## 0. 数字来源索引

| 数字 | 值 | 来源 | 状态 |
| --- | --- | --- | --- |
| 后端测试 | 540 passed / 9 skipped，覆盖率 ≥87%（`fail_under`） | docs/prd.md §10.2、docs/control/project-index.md（2026-10 对齐代码） | ✅ 已实现 |
| 前端测试 | 189 passed / 31 files；覆盖率 90.00 / 82.92 / 85.27 / 90.00 过四阈值（76/74/78/76） | docs/control/project-index.md 最新进度快照（2026-10-11 收口批次） | ✅ 已实现 |
| 构建产物 | CSS 83.2 kB → 58.7 kB | 同上 | ✅ 已实现 |
| Alembic 迁移 | 13 个版本 | docs/prd.md §6.2 | ✅ 已实现 |
| 生产门控 | 17 项启动清单，缺一拒绝启动 | docs/prd.md §7.5 | ✅ 已实现 |
| 语音 think 代理限流 | 120 次 / 5 分钟 / 会话 | docs/prd.md §4.7 | ✅ 已实现 |
| 单调用输出预算 | coach 300 / feedback 400 / scene 500 / review 300 tokens | `api/core/config.py:99-105` | ✅ 已实现 |
| 文本单轮成本 | $0.0008（gpt-4o-mini）~ $0.0022（gpt-4.1-mini） | 02 文档 §3.5 估算（定价锚点 2024-07 / 2025-04 官方价） | ⚠️ 估算（输入 token 均值待实测） |
| 语音会话成本 | ≈$0.51 / 10 分钟（Deepgram Growth $0.05/min + think ≈10 轮） | 02 文档 §3.5（Deepgram 定价：vendor 自述，2026-07） | ⚠️ 估算 |
| 语音级联延迟 | ≈1–2s / 轮（EOT + LLM TTFT + TTS 首包） | 02 文档 §3.5 预算表 | ⚠️ 估算——**待补：测法：P0 在 think 代理与收口路径打点后，用 OTel span 直方图出 P50/P95** |
| 文本轮首响 | 2–4s 目标 | 同上 | ⚠️ 目标值——**待补：同一 span 数据** |
| 用户量 / 留存 | 无 | 本项目是作品集项目，无真实用户数据 | ❌ **任何简历与面试表述中不得出现** |

---

## 版本 A · 现状版（今天就能贴）

### A.1 30 秒面试口述版

**中文**：
> EchoWhale 是我独立开发的情景式英语口语陪练系统：上传一张生活场景图片，视觉模型识别场景生成角色和开场白，然后进行角色化多轮英文对话（SSE 流式），每轮返回 Grammar / More Natural / Useful Words 三类结构化反馈，支持 Deepgram 实时语音练习，练习数据沉淀为学员档案（CEFR 滚动估计 + 9 类错误画像）再注入后续提示词形成个性化闭环。工程上它不是一个 prompt 套壳：FastAPI 分层 + 四个 agent engine，每个 LLM 调用有主备双通道 failover 和独立的失败语义——教练失败整轮不落库、反馈失败降级占位卡、复盘失败降模板，用户永远能继续练习；540 个后端测试、覆盖率 87% 起，mock/live 双运行时让整个系统零外部依赖可开发可测。

**English**:
> EchoWhale is a scenario-based English speaking-practice system I built end-to-end: upload a photo, a vision model turns it into a scene with a role and an opening line, then you have a multi-turn role-play conversation over SSE streaming — every turn returns structured feedback (Grammar / More Natural / Useful Words), and Deepgram powers real-time voice practice. Practice data rolls into a learner profile (a rolling CEFR estimate plus a 9-category error profile) that is injected back into the prompts, closing the personalization loop. Engineering-wise it's not a prompt wrapper: a layered FastAPI backend with four agent engines, primary/fallback failover on every LLM call, and layered failure semantics — coach failure fails the whole turn, feedback failure degrades to a placeholder card, review failure degrades to a template — so the learner can always keep practicing. 540 backend tests at ≥87% coverage, and a mock/live dual runtime lets the whole system run with zero external dependencies.

### A.2 STAR 四段展开

**Situation（真实痛点）**
中文：口语练习产品的单轮回复背后是 4 类 LLM 调用（场景理解 / 教练 / 反馈 / 复盘）加语音、对象存储、数据库等外部依赖；早期骨架版本任何一处失败都会让整轮对话挂掉，而外部模型 API 的可用性和延迟是不可控的。作为要写进简历的开源作品，它还必须让面试官在 10 分钟内看懂架构、本地零依赖跑起来。
English: One turn of a speaking-practice product hides four LLM calls (scene / coach / feedback / review) plus voice, object storage and database dependencies; in the early skeleton, any single failure broke the whole turn — while model API availability and latency are outside my control. As a resume-grade open-source project, it also had to be understandable in ten minutes and runnable locally with zero external dependencies.

**Task（约束）**
中文：单人交付全栈产品，约束三条：① 成本可控——每次调用有 token 硬顶与全局限流；② 诚实降级——增强能力失败不许拖垮主价值；③ 工程可信——分层测试门禁 + 生产配置门控。
English: Ship the full stack alone under three constraints: (1) bounded cost — per-call token caps plus global rate limiting; (2) honest degradation — enhancement failures must never take down the main value; (3) engineering credibility — layered test gates and a production config gate.

**Action（技术选型理由）**
中文：① 四个 agent engine（scene/coach/feedback/session）统一 agent.py + schema.py + service.py + prompts/ 结构，schema 即契约；② 每类调用主备双通道 + 重试 + deadline（`run_llm_with_failover`），而不是简单的 try/except——流式路径只在「开流」阶段参与重试，开流后不整体重来；③ 失败语义分层写进编排层与 OTel 终态（ok/degraded/failed），反馈与教练用 `asyncio.gather(return_exceptions=True)` 并发——一侧失败不取消另一侧已计费的调用；④ 学员档案走「LLM 输出 → 9 类封闭集合写侧防御 → CEFR 下中位滚动估计 → 有界注入块」的闭环，提示词注入面不扩大；⑤ 语音链路 Deepgram 级联（Flux 听 + BYO think 经后端代理 + Aura-2 说），think 代理令牌与语音会话代数绑定，收口尾段去重；⑥ mock/live 双运行时 + 17 项生产门控 + OTel 三层 span；⑦ 三座离线评测台（样例集 + 硬规则 + LLM judge）驱动提示词修正。
English: (1) four agent engines with a uniform agent.py/schema.py/service.py/prompts structure where the Pydantic schema is the contract; (2) primary/fallback dual-channel with retry and deadline per call — and on the streaming path, retries apply only to opening the stream; (3) layered failure semantics encoded in both the orchestrator and OTel terminal states, with feedback and coach running concurrently via `asyncio.gather(return_exceptions=True)` so one side's failure never cancels the other's paid call; (4) the learner profile loop: LLM output → 9-category closed set with write-side defense → rolling lower-median CEFR estimate → bounded prompt injection; (5) Deepgram cascaded voice (Flux listening + BYO think via a backend proxy + Aura-2 speech), with proxy tokens generation-bound to the voice session and transcript tail-dedup on completion; (6) mock/live dual runtime, a 17-point production gate, and three-layer OTel spans; (7) three offline eval benches (sample sets + hard rules + an LLM judge) driving prompt fixes.

**Result（可量化、可验证）**
中文：后端 540 tests 全绿、覆盖率 ≥87%（pyproject `fail_under` 强制）；前端 189 tests、四阈值覆盖率 90.00/82.92/85.27/90.00 全过；CSS 产物 83.2→58.7 kB；13 个 Alembic 迁移；单调用输出 token 硬顶 300–500、语音 think 代理 120 次/5 分钟——成本上界可预算（文本单轮估算 $0.001–0.002，来源见 §0）。全部数字来自仓库公开门禁与文档，面试现场可复跑 `uv run pytest tests --cov=api` 验证。
English: 540 backend tests green at ≥87% enforced coverage; 189 frontend tests passing four coverage thresholds (90.00/82.92/85.27/90.00); CSS bundle down 83.2→58.7 kB; 13 Alembic migrations; per-call output caps of 300–500 tokens and voice think-proxy rate limits of 120/5 min make cost upper bounds explicit (≈$0.001–0.002 per text turn, estimated — see §0). Every number comes from the repo's public gates and docs, and can be re-verified live with `uv run pytest tests --cov=api`.

### A.3 简历 bullets（现状版）

**中文（3–5 条）**
1. **设计并实现**情景式英语口语陪练系统 EchoWhale 全栈架构（FastAPI 分层 + React 19），四个 LLM agent engine 统一「agent/schema/service/prompts」模块契约，540 后端测试 / 覆盖率 ≥87% 门禁强制。
2. **实现**LLM 主备双通道 failover（重试 + deadline + 流式开流期重试）与分层失败语义（教练 failed / 反馈 degraded / 复盘 degraded），用户可感知的对话可用性不依赖单一模型可用性。
3. **构建**学员档案数据闭环：LLM 输出经 9 类封闭错误集合写侧防御与 CEFR 下中位滚动估计，生成有界注入块反哺教练 / 反馈 / 语音 think 三处提示词。
4. **接入**Deepgram 实时语音 Agent（Flux + BYO think 代理 + Aura-2）：代理令牌与语音会话代数绑定收敛重放窗口，收口尾段转写去重，think 代理按会话限流 120 次/5 分钟。
5. **搭建**可观测与评测基建：OTel 三层 span（server/engine/llm.attempt）+ llm_usage token 账本 + 三座离线评测台（样例集 + 硬规则 + LLM judge），支撑评测驱动的提示词修正流程。

**English (3–5 bullets)**
1. **Architected and shipped** EchoWhale, a full-stack scenario-based English speaking-practice system (layered FastAPI + React 19) with four LLM agent engines under a uniform agent/schema/service/prompts contract, enforced by 540 backend tests at ≥87% gated coverage.
2. **Implemented** primary/fallback LLM failover (retry + deadline + stream-open-phase retries) with layered failure semantics (coach=failed, feedback=degraded, review=degraded), so conversation availability never depends on a single model's availability.
3. **Built** the learner-profile data loop: LLM output → 9-category closed error set with write-side defense → rolling lower-median CEFR estimate → bounded prompt injection back into the coach, feedback and voice-think prompts.
4. **Integrated** the Deepgram real-time voice agent (Flux + BYO think proxy + Aura-2): proxy tokens generation-bound to each voice session to shrink replay windows, transcript tail-deduplication on completion, and per-session think-proxy rate limiting (120 req/5 min).
5. **Established** observability and evaluation infrastructure: three-layer OTel spans (server/engine/llm.attempt), a per-model token ledger, and three offline eval benches (sample sets + hard rules + LLM judge) powering an eval-driven prompt-fix workflow.

---

## 版本 B · 目标版（多 Agent 改造完成后）

> 使用纪律：**逐条标注前置期数，完成该期并合入主线之前，对应 bullet 不得写入简历。**

### B.1 30 秒面试口述版

**中文**：
> 在原有单链路流水线的基础上，我把 EchoWhale 升级成了显式的多 Agent 协作架构：先是把编排层重构为 Agent 协议 + 注册表（P0），任何 agent 可插拔、可降级、可观测；然后新增发音教练——语音会话中逐轮音素级发音评估，坚持延迟纠错原则不打断对话流（P1）；再加上记忆管理员与课程规划师，把单轮结果事件化为跨会话记忆（掌握/卡壳/复习），驱动「上次卡壳的场景今天再练一次」的学习路径推荐（P2）。全链路复用既有的失败语义分层与 mock/live 双运行时，新增 agent 全部是增强分支——发音评估挂了隐藏分区，课程建议缺席就自由选场景，主对话永远不断。

**English**:
> I upgraded EchoWhale from a single-pipeline LLM app into an explicit multi-agent architecture: first refactoring the orchestration layer into an Agent protocol + registry (P0), making every agent pluggable, degradable and observable; then adding a Pronunciation Coach doing per-turn phoneme-level assessment inside voice sessions — delayed correction, never interrupting the conversation flow (P1); then a Memory Manager and Curriculum Planner that turn per-turn outcomes into cross-session memory events (mastered / stuck / review), driving recommendations like "you got stuck on conditionals at the coffee shop — retry it today" (P2). Everything reuses the existing layered failure semantics and mock/live dual runtime: new agents are enhancement branches only — if pronunciation fails the section hides, if curriculum advice is missing you just pick a scene freely — the main conversation never breaks.

### B.2 STAR 四段展开

**Situation**
中文：升级前的系统是「模块化 LLM 调用流水线」：四个 engine 之间是硬编码并发调用，没有协作协议；口语产品的「说」没有质量反馈（无发音评估）；档案只有统计画像没有跨会话记忆；继续加 agent 只会让 990 行的编排上帝类加速腐化。
English: Before the upgrade the system was a modular LLM pipeline: engines were wired by hardcoded concurrent calls with no collaboration protocol; the "speaking" half of a speaking product had no quality feedback (no pronunciation assessment); the profile was statistics without cross-session memory; and every new agent would accelerate the decay of a 990-line god-class orchestrator.

**Task**
中文：在不推倒重来的硬约束下（540 个测试是回归网，不是包袱），把系统升级为多 Agent 协作架构，并且每一期都要有可验收的用户故事与门禁标准。
English: Upgrade to a multi-agent architecture under a hard no-rewrite constraint — the 540 tests are a regression net, not baggage — with acceptance-grade user stories and gate criteria for every phase.

**Action**
中文：① 调研后**自研轻量协作层**而不用 LangGraph/Agents SDK/CrewAI：一轮对话是确定性管道 + 并行分支（Anthropic《Building effective agents》2024-12 的判断标准），图运行时收益为零、迁移成本是重写全部编排语义；② 发音教练选 Azure Pronunciation Assessment 做 live provider、本地 mock 同构实现，坚持 mock/live 双运行时纪律，发音评估挂在收口后异步路径，think 链路 P95 无可测退化；③ 记忆层自研 `memory_events` 事件表而不用 Mem0/Zep：学习记忆是结构化教育事实（9 类封闭集合哲学的延续），第三方记忆服务引入新延迟面且 $19–375/月的档位不成比例；④ 语音保持 Deepgram 级联而非换 OpenAI Realtime 端到端：Deepgram 连接计价（$0.05/min）可预测、pipeline 可观测、BYO think 正是 agent 接入点——端到端方案降级为 P2 备选。
English: (1) After research I built a lightweight in-house collaboration layer instead of adopting LangGraph / OpenAI Agents SDK / CrewAI: one conversation turn is a deterministic pipeline plus parallel branches (the Anthropic "Building effective agents" criterion, Dec 2024) — a graph runtime buys nothing here and would mean rewriting every orchestration semantic; (2) the Pronunciation Coach uses Azure Pronunciation Assessment as its live provider with a structurally identical local mock, keeping the mock/live discipline, and runs asynchronously after turn completion so the think-path P95 shows no measurable regression; (3) the memory layer is a self-built `memory_events` table rather than Mem0/Zep: learner memory is structured educational fact (an extension of the 9-category closed-set philosophy), and third-party memory services add a latency surface at $19–375/month that the value doesn't justify; (4) voice stays on the Deepgram cascade instead of switching to OpenAI Realtime end-to-end: connection-time pricing ($0.05/min) is forecastable, the pipeline stays observable, and BYO-think is precisely where agents plug in — the end-to-end route is demoted to a P2 fallback.

**Result**
中文（完成 P0–P2 后全部可验证）：① 新 agent 以协议注册接入，编排主干零改动（P0 验收：新增协作层单测 ≥15 条，540+ 全绿）；② 语音会话每轮产出发音分数与问题音，收口复盘含发音分区，评估失败 UI 隐藏分区、零主链路影响（P1）；③ 跨会话记忆事件驱动课程推荐，/progress 页呈现成长轨迹（P2）；④ 成本上界：文本单轮估算 $0.001–0.002、语音会话 ≈$0.51/10 分钟（来源 §0）；⑤ 端到端语音延迟 1–2s 量级并有 span 直方图佐证（**待补：P0 打点后实测替换**）。
English (all verifiable after P0–P2): (1) new agents register via the protocol with zero orchestrator-core changes (P0 gate: ≥15 new collaboration-layer tests, 540+ all green); (2) every voice turn yields a pronunciation score and problem phonemes, the review page gains a pronunciation section, and an assessment failure hides the section with zero main-path impact (P1); (3) cross-session memory events drive curriculum recommendations and a growth trajectory on /progress (P2); (4) cost upper bounds: ≈$0.001–0.002 per text turn and ≈$0.51 per 10-minute voice session (estimated, source §0); (5) end-to-end voice latency in the 1–2s range backed by span histograms (**待补 to be replaced with measured data after P0 instrumentation**).

### B.3 简历 bullets（目标版，逐条标前置期）

**中文**
1. 〔需 **P0**〕**重构**会话编排层为显式多 Agent 协作架构（Agent Protocol + 注册表 + 三值终态 ok/degraded/failed），新 agent 插拔零改编排主干，540+ 测试作为回归网全量保留。
2. 〔需 **P1**〕**设计并实现**发音教练 agent：Azure Pronunciation Assessment 音素级评估 + mock/live 双 provider，语音会话逐轮异步评估实现延迟纠错（不打断对话流），失败语义为 UI 隐藏分区、主链路零影响。
3. 〔需 **P2**〕**构建**跨会话记忆层（memory_events 掌握/卡壳/复习事件，纯函数更新 + 写侧封顶）与课程规划师 agent，驱动「卡壳场景再练一次」式学习路径推荐；评估后弃用 Mem0/Zep（成本与延迟面不成比例）并记录决策依据。
4. 〔需 **P2**〕**接入** Langfuse（原生消费 OTLP）补齐 LLM 观测，三 agent 协作链路全链路可追踪；语音级联延迟有 span 直方图基线（P50/P95）。
5. 〔需 **P0–P2** 任一里程碑〕**量化**成本与延迟预算：文本单轮 $0.001–0.002（token 硬顶 + 模型分级 + 缓存三重护栏）、语音会话 ≈$0.51/10 分钟、端到端延迟 1–2s（估算→实测，来源见 02 文档 §0/§3.5）。

**English**
1. [**P0**] **Refactored** the session orchestration layer into an explicit multi-agent architecture (Agent Protocol + registry + three-valued terminal states ok/degraded/failed); new agents plug in with zero orchestrator-core changes while all 540+ tests remain the regression net.
2. [**P1**] **Designed and built** a Pronunciation Coach agent: phoneme-level assessment via Azure Pronunciation Assessment with mock/live twin providers, per-turn asynchronous scoring inside voice sessions enabling delayed correction (never interrupting the flow), failing safe to a hidden UI section with zero main-path impact.
3. [**P2**] **Built** a cross-session memory layer (memory_events: mastered/stuck/review events with pure-function updates and write-side caps) plus a Curriculum Planner agent driving "retry your stuck scenario" learning paths; documented the decision to reject Mem0/Zep on cost and latency-surface grounds.
4. [**P2**] **Integrated** Langfuse (native OTLP consumer) to complete LLM observability, with full tracing across the three-agent collaboration and a span-histogram latency baseline (P50/P95) for the voice cascade.
5. [**P0–P2** milestone] **Quantified** cost and latency budgets: ≈$0.001–0.002 per text turn (triple guardrails: token caps + model tiering + caching), ≈$0.51 per 10-minute voice session, and 1–2s end-to-end voice latency (estimate → measured; sources in doc 02 §0/§3.5).

---

## 面试预答：数字哪来的？

| 可能的追问 | 回答 |
| --- | --- |
| 「540 个测试怎么来的？」 | 后端三层门禁（smoke/module/integration），`uv run pytest tests --cov=api` 本地可复跑；覆盖率 87 是 pyproject `fail_under` 硬门禁，低于即 CI 红。 |
| 「$0.51/10 分钟怎么算的？」 | Deepgram Growth 档 $0.05/min 连接计价（vendor 定价页，2026-07）× 10 分钟 = $0.50，加 think 调用 ≈10 轮 × 文本单轮估算 ≈$0.01。**诚实标注：这是估算不是账单**，实测方法已写进 02 文档 §3.5（llm_usage 账本按 prompt_tokens 聚合）。 |
| 「1–2s 延迟测过吗？」 | 目前是分段的量级估算（EOT 数百 ms + LLM TTFT 300–900ms + TTS 首包 100–300ms），**还没有端到端实测**——P0 第一个交付就是把 span 打点补齐，用直方图出 P50/P95。我不会把估算说成实测。 |
| 「为什么不用 LangGraph？」 | 见 02 文档 §2.1：确定性管道用不上图运行时；Anthropic 官方指南同判断；迁移成本是重写全部编排语义与测试锚点。 |
| 「为什么不用 Mem0？」 | 学习记忆是结构化教育事实不是开放对话事实；自研事件表延续 9 类封闭集合的写侧防御哲学，零新延迟面；Mem0/Zep 的 LoCoMo 分数解决的是我没有的问题。 |
| 「用户量多少？」 | 作品集项目，没有真实用户数据——我不会编。有数据的是工程面：测试数、覆盖率、成本上界、降级行为，全部可复跑验证。 |
