# 市场对标、稳定性保障与架构修订 v1.1（多 Agent 升级 · 增补）

> 检索日期：2026-10-28。上游文档：[01](01_gap_analysis.md) / [02](02_target_architecture.md) / [03](03_star_introduction.md)。
> 本文回答三个问题：① 新架构相对旧架构的优势是什么；② 每个 agent 的稳定性与可评测性如何保障；
> ③ 对标同类产品与业界 agent 架构后，目标架构与项目介绍如何修订。
> 修订项编号 R1–R6 是对 02 文档设计的增量（v1.1），各自标注所属期数。

## 1. 新旧架构优势对照

> 诚实性标注：「新」列是设计目标，对应期数交付并过验收后才成立（见 02 §3.4）。

| 维度 | 旧：单链路流水线 | 新：多 Agent 协作层 | 前置期 |
| --- | --- | --- | --- |
| 新 agent 接入 | 改 `session_engine/agent.py`（990 行上帝类）的编排逻辑 | 实现 Agent Protocol + 注册表登记，编排主干零改动 | P0 |
| 失败语义 | 隐含在编排代码各处（虽有一致约定，靠人读代码背） | 类型化三值终态 ok/degraded/failed，每个 agent 的降级路径是协议签名的一部分 | P0 |
| 可评测性 | 三座评测台存在但 feedback 缺位、手动触发 | 每 agent 一座同构评测台（硬规则在线 + judge 门控 + 定时回归） | P0–P2 |
| 能力面 | 文字反馈单一维度 | +发音评估（P1）、+跨会话记忆与课程规划（P2） | P1–P2 |
| 成本治理 | 单调用 token 硬顶 | 上述 + 每 agent 预算与会话级预算硬顶（R2） | P0 |
| 简历叙事 | 「多 agent」无实体支撑 | 协议、失败语义、评测矩阵、预算护栏全套可验证实体 | P0–P2 |
| 面试可辩护性 | 「你的 agent 怎么协作」只能答函数调用 | 可画图（02 §3.2）、可引证（Anthropic 失效模式研究）、可跑测试 | P0 |

## 2. 每个 Agent 的稳定性与可评测性保障

### 2.1 四道稳定性防线（对所有 agent 生效）

1. **契约防线**：agent 间只传 Pydantic 已验证结构——结构不对就进不了下一个 agent。这是对
   LLM 幻觉级联的直接防御；先例已在线上：9 类错误封闭集合的写侧防御把模型幻觉 category 静默丢弃
   （`learner_profile.py:88`），schema 校验失败按可重试 provider 错误处理（`feedback_engine/agent.py:87`）。
2. **依赖防线**：每个 LLM 型 agent 继承主备双通道 + 指数退避重试 + deadline（`run_llm_with_failover`）；
   流式路径只在「开流」阶段参与重试，开流后中断不整体重来（`coach_engine/agent.py:53-73`）。
3. **语义防线**：编排者-工作者、永不对等（R1，见 §4）——每个 agent 是被 Orchestrator 调用的工具型
   工作者，输入输出是协议签名的一部分，**不存在 agent 互调与自由协商**。依据：Anthropic 对多 agent
   系统的实证研究（2026-08-13，《Patterns and problems in emerging multiagent systems》）表明，
   「把其他 agent 当工具调用（well-defined inputs/outputs）时协作高效；把彼此当长生命周期对等主体时
   出现从属失效、共谋与地盘战争」。教育对话轮是确定性流程，可预测性优先于自主性——本架构从拓扑上
   排除了对等协作的三类失效面。
4. **观测防线**：三值终态逐 agent 打 engine span；`degraded=true` 日志标记区分「降级成功」与
   「正常生成」；llm_usage 账本按模型/天聚合 token（P2 接 Langfuse 消费 OTLP 后补全链路视图）。

### 2.2 逐 agent 稳定性 × 评测矩阵

| Agent | 失败时用户看到 | 稳定性机制（现状/新增） | 评测手段 | 归属期 |
| --- | --- | --- | --- | --- |
| Conversation Coach | 整轮失败提示重试，不落库 | 主备 failover + 2000 字符硬顶（现状） | coach 评测台：5 维硬规则（english_only/长度/follow_up/meta 泄漏/不复读）+ judge（角色贴合/CEFR 适配/一小步拉伸），live 门控 RUN_COACH_EVAL | 已上线 |
| Feedback Coach | 占位反馈卡（如实标注本轮失败） | 主备 failover + JSON 校验失败按可重试错误（现状） | **P0 新增**评测台：9 类闭包校验、JSON 合法率、长度、错误归类准确率抽样 judge | P0 |
| Pronunciation Coach | 隐藏发音分区，文字反馈不受影响 | 新增：专用 API 超时即降级；mock provider 与 live 同构 | 新增评测台：分数区间、音素集闭包硬规则 + 诊断文案 judge + 金标准音频样例集 | P1 |
| Curriculum Planner | 建议缺席，自由选场景 | 新增：每会话 ≤2 次调用 + token 预算 | 新增评测台：judge（建议与档案一致性、场景 ∈ 场景库） | P2 |
| Memory Manager | 回退现有档案静态注入 | 纯函数 + 写侧封顶（继承 learner_profile 设计） | 纯函数确定性单测 + 注入面有界性测试 | P1–P2 |
| Review Summarizer | 模板复盘 | 5s 有界等待（现状） | session 评测台五维硬规则（全确定性，无 judge） | 已上线 |
| Orchestrator | 编排 bug = 整轮失败（代码，无模型） | 协议单测锁定事件序 | P0 验收：协作层新增单测 ≥15 条；540 存量测试作回归网 | P0 |

### 2.3 可评测性三原则

1. **同构评测台**：每 agent 一座「固定样例集 + 硬规则 + 可选 LLM judge + JSONL 逐案重放落盘」，
   形态对齐已上线的 coach/scene/session 三台（`api/modules/*/evaluation.py`）。
2. **硬规则永远在线，judge 门控运行**：硬规则进 CI 常规单测（零外部依赖）；judge 走 live 门控，
   R5 升级为定时回归。
3. **评测驱动修正闭环已验证**：仓库既有流程（live 首跑 → 疑似问题分诊 → 提示词/护栏修正 → 复跑达标，
   见 `docs/features/eval_prompt_fixes/`，6/6 达标）是评测可评测性的实证。

## 3. 市场扫描：同类产品与空位（检索 2026-10）

| 产品 | 核心形态 | 强项 | 公开信息日期 |
| --- | --- | --- | --- |
| **Speak** | OpenAI 官方合作案例（openai.com，2025-04）；「AI 导师记得你」（App Store 文案）、发音/语调/流利度评估、live role-play | 结构化课程 + 个性化记忆 + 会话评估 | 2025-04 ~ 2026 |
| **ELSA Speak** | 发音评分品类标杆：ASR 音素级评估、即时个性化反馈、8000+ 课时 | 发音维度深度 | 2025-01（ResearchGate 论文确认 ASR 评估路线） |
| **Duolingo Max** | Video Call with Lily + Roleplay（GPT-4，2023-03 上线） | 免费习惯养成 + 角色化对话 | 2023-03 ~ 2026-07；社区口碑（Reddit/Facebook 2025-2026）：固定场景的 Roleplay 好于开放 Video Call，但对话常被评生硬 |
| **TalkPal** | 130+ 语言、语音+聊天双模式 | 语言广度 | 2026（Google Play 4.6 分） |
| **Praktika / Langua / Fluently** | AI 头像会话 / intermediate 口语口碑最佳 / 职场英语细分 | 细分定位 | 2026-03 ~ 2026-09 横评（lingtuitive、upskillist、getfluently） |

**市场空位 → EchoWhale 的三条差异化**：

1. **场景来自学习者自己的生活**：横评内所有产品都依赖**内置课程与固定场景库**（Speak 的 lesson、
   ELSA 的 8000 课时、Duolingo 的 Roleplay 预设）——无一支持「上传一张你今天拍的真实照片，
   即时生成专属情景对话」。EchoWhale 的视觉→场景→角色→开场白链路练的是「你明天真的会遇到的那家
   咖啡店」。（诚实标注：这是产品定位差异，不是技术壁垒——壁垒在链路工程化质量。）
2. **可验证的工程治理**：竞品闭源、不公开失败语义/评测/可观测设计；EchoWhale 开源 mock/live
   双运行时、分层失败语义、三座评测台、540 测试门禁——对作品集与面试场景，这是竞品没有的卖点。
3. **延迟纠错教学法**：练习流不被打断，练后给结构化反馈（与 Speak 的 live 即时打断纠错形成方法论
   差异）；P1 发音、P2 记忆/规划交付后，反馈维度对齐头部体验（ELSA 的发音、Speak 的记忆）。

## 4. 业界 agent 架构借鉴 → 架构修订 v1.1（R1–R6）

| # | 修订项 | 依据 | 归属期 |
| --- | --- | --- | --- |
| **R1** | **「编排者-工作者，永不对等」成文为设计原则**：禁止 agent 互调，全部路由经 Orchestrator；写入 02 文档 §3.1 与未来模块 README | Anthropic 2026-08：工具型调用可靠，对等自治出现 conformity（同错放大）/共谋/地盘战争三类失效 | P0 |
| **R2** | **每 agent token 预算 + 会话级预算硬顶**：settings 新增 per-agent budget；会话超限 → 增强分支跳过 / 降小模型，教练分支永不因预算失败 | Anthropic 多 agent 研究系统工程博客（2025-06）：多 agent 系统 token 消耗约为单 agent 聊天的 15×，预算必须显式管理；呼应 G9 | P0 |
| **R3** | **语音逐轮反馈落点修订**：利用 Deepgram Voice Agent 内建 function calling（vendor 产品页，2026）作为对话教练在会话内请求「发音微反馈/词汇提示」的通道；音素级完整评估仍在收口后异步——修正 02 文档「收口后统一评估」的单点入口，逐轮体验对齐 Speak/ELSA | Deepgram 产品页（2026）确认 function calling 内建；市场对标 §3 | P1 |
| **R4** | **memory_events 增加复习调度字段**（简化 SM-2：interval / ease / due_at），课程规划师按到期事件出题——形成「练习 → 记忆 → 到期复习」闭环 | 间隔复习是 Duolingo/ELSA 等头部产品的标配能力（横评 §3）；补齐 G5 时对齐行业标准 | P2 |
| **R5** | **评测升级为定时回归**：weekly live eval job 复跑全部评测台 + judge，结果落 `docs/features/<slug>/` 留痕 | G8 的「手动跑」升级为「定时 + 门禁」；对齐 eval_prompt_fixes 已验证的评测驱动修正流程 | P0（feedback 台随建随跑） |
| **R6** | **评测增加「同输入方差」检查**：同一 live 用例跑 3 次，硬规则须 3/3 通过——低方差 agent 的同错会被同一样例集放大，需要显式检出 | Anthropic 2026-08 conformity 发现的轻量工程落地 | P1 |

**结论重申（应对面试拷问「为什么你的架构不需要更自治的 agent 协作」）**：一轮教学对话的可预测性
价值高于自主性价值；Anthropic 2026-08 的实证与 2025-06 的工程经验（预算、并行、评测驱动）全部
指向「编排者-工作者 + 显式契约」这一档。若未来课程规划师需要真正的多步自主规划，再在
curriculum_engine 内局部引入工具循环（02 §2.1 的 PydanticAI 备选仍保留）。

## 5. 项目介绍优化 v2

### 5.1 30 秒口述版（v2，中英）

**中文**：
> EchoWhale 是我独立开发的情景式英语口语陪练系统，差异点在场景来源：Speak、ELSA、Duolingo Max
> 练的都是内置课程和固定场景库，EchoWhale 让你上传一张自己拍的照片——咖啡店、办公室、机场——
> 视觉模型即时把它变成一场角色化英语对话，SSE 流式多轮练习，每轮给 Grammar / More Natural /
> Useful Words 结构化反馈，实时语音由 Deepgram 驱动。工程上它按多 agent 架构组织：对话教练、
> 反馈教练、发音教练、课程规划师、记忆管理员各司其职，编排层是显式协议 + 三值失败语义
> （ok/degraded/failed），每个 agent 有独立评测台；540 个后端测试、覆盖率 87% 起、mock/live
> 双运行时，零外部依赖可本地复跑。

**English**:
> EchoWhale is a scenario-based English speaking-practice system I built solo, and its differentiator
> is where scenarios come from: Speak, ELSA and Duolingo Max all practice against built-in courses and
> fixed scene libraries — EchoWhale lets you upload a photo you took today (a café, an office, an
> airport) and a vision model instantly turns it into a role-played English conversation, streamed over
> SSE with structured feedback every turn (Grammar / More Natural / Useful Words), with real-time voice
> powered by Deepgram. Architecturally it's organized as cooperating agents — conversation coach,
> feedback coach, pronunciation coach, curriculum planner, memory manager — behind an explicit protocol
> with three-valued failure semantics (ok/degraded/failed) and a dedicated eval bench per agent; 540
> backend tests, ≥87% enforced coverage, and a mock/live dual runtime that runs locally with zero
> external dependencies.

### 5.2 定位句与 bullets 增补（并入 03 文档使用）

- **一句定位**：EchoWhale = 「你的生活就是教材」的情景口语陪练 + 可验证的多 agent 工程治理。
- 〔需 P1〕发音维度对齐 ELSA 品类标杆：音素级评估 + 延迟纠错（不打断练习流）。
- 〔需 P2〕记忆与复习调度对齐 Speak/Duolingo 头部体验：掌握/卡壳事件 + SM-2 到期复习（R4）。
- 〔现状即可讲〕开源可验证性是竞品没有的叙事：任何面试官可以 clone 仓库复跑测试与评测台。

### 5.3 面试拷问预答增补

| 追问 | 回答 |
| --- | --- |
| 「为什么不让 agent 之间自主协商？」 | Anthropic 2026-08 实证：对等协作出现同错放大、共谋与目标冲突；工具型调用（well-defined I/O）才是当前可靠形态。教学对话轮是确定性流程，可预测性 > 自主性（R1）。 |
| 「多 agent token 翻倍，成本怎么控？」 | 四重护栏：单调用输出硬顶（300–500 tokens）+ 每 agent 预算与会话级硬顶（R2）+ 模型分级（教练大模型、其余中小/专用）+ 调用频次上限（curriculum ≤2 次/会话）。Anthropic 自己的多 agent 系统消耗 15× token，预算必须显式管理——这是他们的工程教训，我直接采纳。 |
| 「和 Speak 比你的壁垒是什么？」 | 场景来源（用户真实照片 vs 内置课程）+ 开源可验证工程。我不宣称技术壁垒——视觉生成情景谁都能做，壁垒在链路的工程化质量（失败语义/评测/可观测/测试门禁），这些仓库里全部可复跑。 |
| 「逐轮发音反馈怎么不打断对话？」 | 双通道：轻量微反馈走 Deepgram function calling（R3），重活（音素级评估）收口后异步——延迟纠错教学法落在产品机制上。 |
