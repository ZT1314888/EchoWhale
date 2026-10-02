# 教学内核提示词升级与 LLM 复盘（teaching_kernel_prompts）

> 审计 Fix Order 16（Finding 20：提示词工程与"教学内核"单薄）修复。
> Trellis 任务：`.trellis/tasks/10-02-teaching-kernel-prompts`。

## 目标

产品"教学大脑"远弱于传输层：反馈系统提示词只有一句话（质量全靠模型临场发挥）、教练提示词无学员水平注入位与输出约束、复盘由 5 个硬编码场景套中文模板生成（live 未知场景如 gym 的标题回退为原始 scene id，next_try 是无关模板句）。本批次把三处提示词/复盘升级为契约化、LLM 驱动的实现，同时保持 mock 模式全链路可跑与前端/API 契约零破坏。

## 实现说明

### 1. 反馈提示词契约化（R1）

- `FEEDBACK_PROMPT` 从一句话扩写为契约式系统提示词：严格 JSON 输出；`errors` 至多 3 项（category 取封闭集合 grammar/tense/article/preposition/word_choice/collocation/register/spelling/other；original 引用原句片段 + correction + 一句 ≤20 词解释）；`grammar` 为面向展示的 `original -> correction (explanation)` 行（≤3 行 ≤320 字符）；`more_natural` ≤2 句；`useful_words` 2–4 个；`cefr_level` 对本次学习者消息的 A1..C2 估计。
- `FeedbackResult` 只加不改：新增可选 `errors: list[FeedbackErrorItem]` 与 `cefr_level: str | None`，均带默认值——mock 路径、降级占位与既有构造不受影响；前端对 feedback 为宽松解析（`??` 兜底），渲染零改动。`cefr_level` 经 field_validator 归一（strip/upper，非 A1..C2 一律归 None，防御模型幻觉值）。
- live 路径 user_prompt 不再重复键清单（避免两处契约漂移），输出契约以系统提示词为单一事实源。

### 2. 复盘 LLM 化（R2，定案：inline 有界等待分支，否决 RQ 异步）

- 定案依据：复盘消费点是"当轮/会话结束即可见"（reply 响应、stream 的 session 事件、语音收口响应），RQ 异步会制造"先模板后 LLM"的内容漂移且需要前端轮询配合，违反前端零改动硬约束；成本两案相同（每轮 +1 次调用），取复杂度最低、一致性最高的 inline 方案（设计权衡详见任务 design.md 第 2.1 节）。
- 新增 `ReviewSummarizerAgent`（`api/modules/session_engine/review_summarizer.py`）：复用反馈引擎的 provider 接线（`resolve_engine_providers` + `TextCompletionProvider` + `run_llm_with_failover` 主备 failover），`max_tokens=llm_review_max_tokens`（新配置键，默认 300），usage sink 构造期默认注入——成本自动进 `llm_usage` 账本。
- 新增 `REVIEW_PROMPT`（`api/modules/session_engine/prompts/review_prompts.py`）：输入 scene/role/learner message/本轮 feedback JSON，输出中文复盘文案 JSON（scene_title/role_label/highlight/next_try/next_step，逐字段长度上限）；明确禁止把原始 scene id 当标题、禁止编造 feedback 之外的内容。
- `ReviewCopy` 契约（review_builder.py）：字段全部 `min_length=1` + strip 前置校验——空串/纯空白/缺键 → ValidationError（ValueError 子类）→ failover 判定可重试 → 主备切换，全败上抛交编排层降级。
- 编排接线（`session_engine/agent.py`）：
  - `reply()`：既有 gather 与失败语义原样保留；coach 确认成功后调用 `_review_copy_for_turn`（内部 `asyncio.wait_for` 有界，`llm_review_wait_seconds` 默认 5s）。
  - `stream_reply()`：feedback 事件后起复盘任务与教练 delta 流并行，delta 消费完对 shield 任务做有界等待——流式主路径近似零附加延迟；失败/超时/提前关闭路径显式取消任务不留悬挂调用。
  - `complete_voice_session()`：会话收口同款接线，同步返回 LLM 复盘。
  - `_review_copy_for_turn` 是单一降级转换点：mock 模式短路零调用 → feedback 已降级跳过（对占位文案做汇总没有意义）→ `except Exception` 捕获超时/failover 全败/未配 provider 的 ConfigurationError，记 `session_review_copy_failed degraded=true` warning 后返回 None（模板复盘）。CancelledError 照常传播，断连语义不变。
- `build_session_review(session, feedback, copy=None)`：`copy=None` 与历史版本行为逐字节一致（模板复盘 = mock 与降级兜底）；copy 提供时替换 highlight/next_try/next_step，消费侧 `_bound` 截断硬顶（120/80/80，提示词是软约束）。
- 未命中 SCENE_COPY 的回退（`get_scene_title`/`get_role_label`）：改"场景名 · 角色名 情景对话"自然语言组合（snake_case 转空格并首字母大写），任何路径不再输出原始 scene id；history 契约的单参调用兼容。

### 3. 教练提示词补强（R3）

- 新增 `COACH_LEARNER_LEVEL = "intermediate (CEFR B1)"` 注入位常量：本期固定中级占位，后续学员状态持久化任务只需把常量改为按用户动态取值，提示词模板不动。
- `COACH_SYSTEM_PROMPT` 增补三行：按注入位声明水平并要求"词汇语法略高于学员水平——可理解、带一点拉伸"；`Reply in English only.`；`at most 3 short sentences plus one follow-up question`（与既有"简洁、可追问"原则一致，合并了原追问行避免重复）。人设与其余指令不动。

### 4. 配置（Finding 10a 同族接线）

- `llm_review_max_tokens=300`（复盘短文案输出预算）、`llm_review_wait_seconds=5.0`（复盘分支对回复轮的最大附加等待，超时取消降级模板）；`.env.example` 同步；均带默认值、不进 `validate_runtime()` 生产清单（复盘可降级，非启动关键项）。

### 5. 测试与离线评测

- 新增 `tests/modules/test_review_summarizer.py`（合法 JSON / 非法 JSON 重试后 failover / 全败 ModelProviderError / max_tokens 与 usage sink 接线）；`test_feedback_engine.py`、`test_session_engine.py`、`test_session_stream.py`、`test_coach_engine.py` 增补：新字段落位与缺省、cefr 归一、提示词契约守卫、mock=模板不回归、live 消费 LLM 文案（含截断硬顶）、summarizer 失败降级 + degraded 日志且轮次成功、feedback 降级跳过 summarizer、流式复盘并行与慢任务取消、未知场景自然语言回退。
- 新增 `tests/modules/test_feedback_engine_live.py`：按 `test_scene_engine_live.py` 模式（`RUN_FEEDBACK_EVAL=1` 门控、CI 默认跳过），5 组固定学习者输入（无错误/时态/冠词介词/用词不当/混合），断言 JSON 结构完整、category ∈ 封闭集合、cefr_level ∈ A1..C2、各字段长度上限、more_natural 非空且异于原句——未来提示词改动的回归评测台。
- 连带治理：锁定工具链（ruff/black 新版本）下 HEAD 存量测试文件本就不过门禁（stdin 实测 HEAD 版本 test_config.py 有 5 处 ruff 违规），本批次顺带完成全仓格式化与 ruff autofix（12 处 unsafe fix 均为测试文件内语义等价改写）。

## 验证

- `uv run pytest tests --cov=api`：477 passed / 7 skipped，覆盖率 88.36%（门禁 87，基线 88.12）。
- `uv run ruff check api tests tools`、`uv run black --check api tests tools`：全绿。
- `RUN_FEEDBACK_EVAL` 未设置时评测文件 skip（5 skipped）；trellis-check 独立复核 10 项全 PASS（Orchestration failure policy、mock 零调用不变量、契约安全、无裸 scene id、跨层数据流、failover/账本接线、配置卫生、测试质量、仓库卫生、门禁数字）。
- mock 模式实证：强制 `MODEL_RUNTIME_MODE=mock` 全量 476 通过——新 LLM 路径零调用。

## 遗留

- `COACH_LEARNER_LEVEL` 仍是固定中级占位：学员状态持久化（CEFR 估计 + 高频错误类型，审计路线图 P2-7）是下一任务，届时改注入位为动态取值。
- `ReviewCopy.scene_title/role_label` 本期不被复盘卡片消费（冗余保留，供未来随契约下发给 history 前端，替代前端 SCENE_META 双份维护——Finding 19 的 Better long-term fix）。
- 复盘 LLM 调用成本观察：上线后看 `llm_usage` 中复盘调用占比与 `session_review_copy_failed degraded=true` 频率，degraded 率过高优先查 REVIEW_PROMPT JSON 合规率。
- `api/tasks/session_summary.py` 死代码桩（Finding 21）维持原状，按审计建议另行删除。
