# 现状审查：能力盘点与差距清单（多 Agent 升级 · 任务 1）

> 依据：docs/prd.md（v0.5，2026-10-03 对齐代码）、docs/control/project-index.md、
> 逐文件代码取证（分支 feature/multi-agent-upgrade-plan，2026-10-28）。
> 成熟度词表：**成熟**（已落地 + 测试门禁覆盖）/ **成型**（已落地，剩余真实环境联调）/ **雏形** / **缺失**。

## 1. 能力盘点表

| # | 能力域 | 成熟度 | 证据（文件路径） |
| --- | --- | --- | --- |
| 1 | 场景理解：视觉模型调用、主备双通道、低置信度门禁（<0.65 拒绝）、缓存 + 提示词版本自愈、RQ 异步 + 202 轮询 | 成熟 | `api/modules/scene_engine/agent.py`、`api/modules/scene_engine/providers/vision_provider.py`、`api/db/scene_analysis_db.py`、`api/tasks/image_analysis.py` |
| 2 | 对话教练：角色化多轮推进、8 轮窗口、CEFR i+1 难度注入、流式/整包双形态、2000 字符输出硬顶 | 成熟 | `api/modules/coach_engine/agent.py`、`api/modules/coach_engine/prompts/coach_prompts.py`、`api/integrations/llm/streaming.py` |
| 3 | 学习反馈：Grammar / More Natural / Useful Words（+Next Step）、9 类封闭错误集合写侧防御、CEFR 观测产出、失败降级占位 | 成熟 | `api/modules/feedback_engine/agent.py`、`api/modules/feedback_engine/schema.py`、`api/modules/feedback_engine/prompts/feedback_prompts.py` |
| 4 | 会话编排：反馈×教练并发、复盘增强分支（5s 有界等待）、失败语义分层（教练 failed / 反馈 degraded / 复盘 degraded）、SSE 事件序、原子落库 + position 唯一约束 | 成熟 | `api/modules/session_engine/agent.py`（990 行，reply / stream_reply / complete_voice_session） |
| 5 | LLM 复盘：单轮中文复盘 + 会话聚合、字段级截断硬顶、场景展示名单一事实源（SCENE_COPY） | 成熟 | `api/modules/session_engine/review_summarizer.py`、`api/modules/session_engine/review_builder.py` |
| 6 | 实时语音：Deepgram Agent 级联（listen=flux-general-en / think=BYO LLM 代理 / speak=aura-2）、令牌 TTL 600s、think 代理令牌与语音会话代数绑定、收口尾段去重 | 成型 | `api/integrations/deepgram/voice_agent.py`、`api/routes/v1/deepgram.py`、`docs/features/deepgram_voice_agent/`、`docs/features/think_token_lifecycle_binding/` |
| 7 | 学员档案：CEFR 滚动估计（最近 10 次观测取下中位）、9 类错误计数、场景频次（cap 12）、读 API + /progress 页、注入教练 / 反馈 / 语音 think 三处提示词 | 成熟 | `api/modules/session_engine/learner_profile.py`（纯函数）、`api/services/learner_profile_service.py`、`docs/features/learner_profile_progress/` |
| 8 | LLM 评测：coach / scene / session 三座评测台（固定样例集 + 硬规则 + judge（scene）/ live 门控 RUN_COACH_EVAL / JSONL 逐案重放）、评测驱动提示词修正流程 | 成型 | `api/modules/coach_engine/evaluation.py`（487 行）、`api/modules/scene_engine/evaluation.py`、`api/modules/session_engine/evaluation.py`、`docs/features/eval_prompt_fixes/` |
| 9 | 可观测：OTel 三层 span（server / engine / llm.attempt）+ 三值终态（ok/degraded/failed）、llm_usage token 账本（按模型/天）、request id 贯穿 | 成熟 | `api/common/telemetry.py`、`api/common/middleware.py`、`api/integrations/llm/resilience.py`、`docs/observability.md` |
| 10 | 工程底座：FastAPI 分层、PG + SQLAlchemy 异步 + Alembic（13 迁移）、Redis + RQ 双队列、R2 直传 + 签名 URL、JWT + 邮箱验证码、统一信封 + 错误码、全局限流、mock/live 双运行时、生产门控 17 项清单 | 成熟 | `api/core/config.py`、`api/common/`、`api/db/`、`api/integrations/`、`docs/features/production_config_gate/` |
| 11 | 前端：React 19 + Vite + TS，11 条路由（上传 / 练习 / 复盘 / 历史 / 进度 / 认证），SSE 流式渲染，语音 UI + TTS 跟读，Vitest 四阈值 90.00 / 82.92 / 85.27 / 90.00 | 成型 | `frontend/src/`、`docs/features/frontend_design_port/` |
| 12 | 测试门禁：后端 540 passed / 9 skipped、覆盖率 ≥87（pyproject fail_under）、ruff + black 全绿；三层测试门（smoke/module/integration）在控制面承载 | 成型 | `tests/`、`pyproject.toml`、`docs/control/project-index.md` 测试门区块 |

**定性结论（与主提示词 §2 一致）**：当前是「模块化 LLM 调用流水线」——四个 engine 是四个**被编排的函数**，
不是四个**自主协作的 agent**。没有 agent 间消息协议、没有动态路由、没有工具调用循环、没有共享记忆层。
「多 agent」的四种成熟形态（prompt chaining / routing / orchestrator-workers / evaluator-optimizer，见 Anthropic
《Building effective agents》，2024-12）中，本项目只落在最基础的 **prompt chaining + 并行化** 一档。

## 2. 差距清单（对照「多 Agent 口语陪练」目标）

| # | 缺口 | 现状证据 | 简历故事哪里立不住 | 产品闭环哪里断掉 |
| --- | --- | --- | --- | --- |
| G1 | **Agent 间协作协议缺失**：engine 间是硬编码 `asyncio.gather` / 顺序调用，无消息契约、无动态路由、无 handoff 语义 | `session_engine/agent.py:321-348`（gather 双分支）、`:732`（语音收口直调 feedback） | 「多 Agent 协作」第一问「你的 agent 之间怎么通信、怎么决定谁出场」只能答「函数调用」；与 LangGraph/OpenAI Agents SDK 简历关键词无实体支撑 | 无法以可插拔方式加入新角色（发音教练、课程规划师）——每加一个 agent 都要改 990 行的上帝编排类 |
| G2 | **发音评估缺失**：PRD §2.3 明确 non-goal，语音链路只做听写转写与收口 | `docs/prd.md` §2.3、`complete_voice_session` 仅对最后一条 learner 消息生成文字反馈 | 「口语陪练」没有发音维度，教育产品故事缺一条腿；「speech 工程深度」只体现为第三方 SDK 接入 | 学员开口练完只得到「对转写文本的文字反馈」，不知道发音哪里差——「说」的质量反馈断裂 |
| G3 | **语音练习无逐轮反馈**：延迟纠错（练完再给反馈）在语音路径只在收口一次性发生；文本路径每轮都有 | `complete_voice_session`（`agent.py:711-810`）只在收口生成一次 feedback；语音进行中无反馈事件通道 | 「延迟纠错教学法」在简历里只能讲文本路径，语音这条主线反而是空白 | 长语音会话（10+ 轮）结束后反馈过载，练习中的可理解性输入 i+1 调整不存在 |
| G4 | **长期记忆层缺失**：档案只有 3 个 JSON 字段的滚动计数（CEFR 窗口 10、场景 cap 12、9 类错误计数），无跨会话语义记忆（掌握过的句型、卡壳的话题、成功经验） | `api/modules/session_engine/learner_profile.py:64-118`、`api/models/learner_profile_model.py` | 「分层记忆系统」关键词只有最浅一层（会话内 8 轮窗口 + 统计画像）；面试官追问「学员上周学的东西这周怎么续上」无答案 | 个性化止步于「难度适配」，无法生成「你上次在咖啡店场景卡在虚拟语气，今天我们再试一次」式的连续学习体验 |
| G5 | **课程规划缺失**：无教学大纲 / 学习路径 / 复习调度，场景选择完全用户驱动 | 全仓库无 curriculum/syllabus/path 相关模块；`docs/prd.md` §2.3 排除「复杂课程系统」 | 产品故事停在「练习工具」，讲不出「学习产品」的成长闭环与 retention 指标 | 学员练完即散，无「下一步练什么」的引导；数据闭环（档案）收了数据却没有规划侧的消费方 |
| G6 | **编排层单点膨胀**：`session_engine/agent.py` 已 990 行、承载回复/流式/语音/历史/档案 8+ 职责；治理文档自认 `inspect.signature` 兼容分派是技术债 | `docs/control/agent-governance.md` 二期技术债、`session_engine/agent.py` 行数 | 面试官看代码会问「这叫多 agent 还是一个上帝类」——架构叙事与代码形态冲突 | 继续叠加 agent 会加速腐化；改一处失败语义要回归全部路径的 540 个测试 |
| G7 | **语音链路可观测不可调优**：barge-in、EOT 阈值（eager 0.4 / 0.7）有配置但无端到端延迟测量、无打断行为数据；OTel span 只覆盖文本链路 | `api/core/config.py:144-161`（deepgram 配置块）、`docs/observability.md`（span 树无 voice 层） | 「语音延迟优化」写不进简历——没有测过任何数字；「可观测性」故事覆盖不了实时链路 | 语音体验是黑盒：卡顿、抢话、误断句无法归因，也无法用数据驱动参数调优 |
| G8 | **评测覆盖不对称**：coach / scene / session 有评测台，feedback_engine 没有；评测为 live 门控手动跑（RUN_COACH_EVAL），未进 CI 定期回归 | `api/modules/`（feedback_engine 无 evaluation.py）、`docs/features/eval_prompt_fixes/` | 「LLM 评测体系」故事只覆盖约 2/3 的 LLM 面；追问「反馈质量怎么回归」会穿帮 | 换模型 / 改反馈提示词时质量回归靠人工抽查；9 类错误归类的准确率从未被度量 |
| G9 | **成本治理粗粒度**：llm_usage 账本按模型/天聚合，无按会话/按用户归因，无预算硬顶（只有单调用 token 上限） | `docs/observability.md` §1、`api/core/config.py:99-105`（各 engine max_tokens 300–500） | 多 agent 后调用数翻倍，「成本怎么控」只能答 token 硬顶，缺预算护栏与归因故事 | 无法回答「一个活跃用户一个月烧多少钱」，商业化与限流策略缺数据支撑 |

## 3. 审查结论

1. **底座强、编排弱**：工程底座（双通道 failover、双运行时、失败语义分层、三层测试门、OTel）达到可写入简历的水平；
   缺的全部集中在「多 agent 化」本身——协作协议（G1）、记忆（G4）、规划（G5）、发音（G2）。
2. **最便宜的下一步是 G1**：把 session_engine 的硬编码编排重构为显式 agent 协作层，是其余所有缺口的前置；
   G2/G4/G5 都要往协作层里挂新 agent。
3. **诚实性提示**：PRD §2.3 把「发音打分」「多 Agent 协作可视化」列为 non-goal——本次升级立项后需同步修订 PRD，
   否则违反「PRD 与代码零矛盾」门禁（docs/prd.md §10.2）。
