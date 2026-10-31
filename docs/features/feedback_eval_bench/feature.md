# 反馈引擎评测台（feedback_eval_bench）

> 多 Agent 升级 P0 验收标准第 4 条（缺口 G8，02_target_architecture.md §3.4）：
> "feedback_engine 补齐评测台（G8），硬规则五维 + live 门控，README 记录首跑结果"。
> 业务 Agent 项目验收卡：`docs/agent-project/acceptance/G8-FEEDBACK-1-评测台.md`。

## 目标

LLM 评测体系此前只覆盖约 2/3 的 LLM 面（coach / scene / session 三台），feedback_engine
是仅有的例外——9 类错误归类的准确率、引用保真度从未被度量，换模型 / 改反馈提示词时
质量回归只能靠人工抽查（G8）。本任务为反馈引擎建立与 coach 评测台形态同构的离线评测：
固定输入样例集 + 硬规则校验器（always-on 单测与 live 门控共用同一组公开纯函数）+
可选 LLM judge + `RUN_FEEDBACK_EVAL=1` 门控 live 评测 + JSONL 逐案落盘与 prompt 哈希绑定。
LLM 评测体系就此覆盖全部四个 LLM 面。

## 实现说明

### 1. 形态同构、代码独立（沿 coach_review_eval_samples 定案）

不抽跨引擎公共层（design.md 1.1 定案）：按引擎各建模块，不 import coach/scene/session
评测台。硬规则校验器的双通道复用在模块内部解决：公开纯函数被 always-on 单测与
gated live 评测 import 同一实现。

### 2. 评测台（`api/modules/feedback_engine/evaluation.py`，纯新增）

- `FeedbackEvaluationCase`：scene / learner_message / vocab_candidates / learner_context
  ——一次 `review()` 调用的完整可重放快照。
- **硬规则五维**（依据 FEEDBACK_PROMPT 字段契约）：
  ① `structure_pass`——errors ≤3、category ∈ 九类封闭集合、original/correction 非空、
  explanation ≤40 词（契约 20 词给 2 倍余量防误杀）；
  ② `quote_fidelity_pass`——每个 `error.original`（strip + 大小写不敏感）是学习者消息
  的子串，编造引用零容忍；
  ③ `grammar_text_pass`——非空、≤320 字符；有错误时行数 == 错误数且每条 original
  在文本中（`original -> correction` 逐行契约的可检验内核）；
  ④ `more_natural_pass`——非空、≤2 句、仅英语（CJK/谚文/假名零容忍）；
  ⑤ `useful_words_pass`——数量 ∈ [2,4]、每项 1-4 个英文 token。
  （`cefr_level` 不设维度：schema 写侧校验已把非法值归一为封闭集合，硬规则恒真无
  信息量——live 观测走 raw_output 与 judge。）
- 可选 `FeedbackJudge`（live-only，`FEEDBACK_EVAL_JUDGE_*` 环境变量，缺省回落 text 主
  provider）：纠正准确 / 更自然 / 词汇有用三维 + reason；judge 故障兜底记 `judge_error`，
  `final_pass` 回落 hard_pass（沿 coach 口径：judge 是增强信号，以硬规则为准）。
- `run_feedback_evaluation`：默认按 settings 构造 text 主槽位 `TextCompletionProvider`
  （json_mode + feedback token 预算，与引擎 live 路径同款装配）；provider 异常兜成
  `graceful_failure` 行（硬规则全 False，通过率显形不静默丢样本）；逐案整文件重放
  写 JSONL，中断不丢已完成样本。

### 3. 单一装配点（唯一的生产代码改动）

user prompt 装配从 `FeedbackEngineAgent._run_live` 内联提取为
`prompts/feedback_prompts.build_feedback_user_prompt`（字节一致，live 链路与评测台
共用），消除评测台与生产装配的契约漂移。系统提示词即 `FEEDBACK_PROMPT` 常量，
prompt 哈希绑定该常量（无每案动态注入，全样例同哈希是预期形态）。

### 4. 样例集与测试

- `tests/fixtures/feedback_eval_cases.json`：8 案——coffee_shop / office / travel /
  restaurant 4 场景 × 无错误 / 时态 / 冠词介词 / 用词 / 混合 5 类错误，含
  learner_context 注入块 2 组、vocab 双空回退分支 1 组；fixture 约束（vocab 0 或 2-4
  个短英文短语）写进 comment 键并由载入测试断言。
- `tests/modules/test_feedback_evaluation.py`：18 条 always-on 单测——五维正反直测、
  mock 全样例通道（显式 pin mock，零模型调用）、prompt 哈希稳定性、fixture 校验、
  折叠函数 graceful_failure / judge 注入分支、runner 逐案落盘与 provider 兜底。
- `tests/modules/test_feedback_engine_live.py`：由内联 5 案直断言升级为评测台形态
  （门控名 `RUN_FEEDBACK_EVAL=1` 不变）；绝对回归项（结构 / 引用保真）= 100%，
  弹性项（hard_pass / final_pass）≥ 0.8（与 coach 评测台同阈值）。

## 首跑结果（2026-10-31，live 门控）

- 命令：`RUN_FEEDBACK_EVAL=1 uv run pytest tests/modules/test_feedback_engine_live.py`
- provider：openai_compatible / `deepseek-ai/DeepSeek-V3.2`（text 主槽位，json_mode，
  max_tokens=400）；无 judge（judge 为可选增强，未启用）
- 样例：8/8 案全部 `actual_outcome=reply`，0 graceful_failure；耗时 438.93s（串行 8 案）
- prompt_hash：`dbad6c6269bc`（FEEDBACK_PROMPT @ 本批次提交版本）

| 维度 | 通过 | 率 | 阈值 |
| --- | --- | --- | --- |
| structure_pass | 8/8 | 100% | 100%（绝对回归项） |
| quote_fidelity_pass | 8/8 | 100% | 100%（绝对回归项） |
| grammar_text_pass | 8/8 | 100% | ≥0.8 |
| more_natural_pass | 8/8 | 100% | ≥0.8 |
| useful_words_pass | 8/8 | 100% | ≥0.8 |
| hard_pass | 8/8 | 100% | ≥0.8 |
| final_pass | 8/8 | 100% | ≥0.8 |

- 结果落盘：`tmp/feedback_engine_eval/results.jsonl`（8 行，逐行 JSON，绑定 prompt_hash）
- 结论：DeepSeek-V3.2 在全部 8 案上零违反五维硬规则——含 learner_context 注入组与
  vocab 双空组；引用保真 100%（无编造 original），九类封闭集合零漂移。基线就此固定，
  后续换模型 / 改 FEEDBACK_PROMPT 以本表为回归对照。

## 门禁

`pytest tests --cov=api`：692 passed / 5 skipped，覆盖率 90.86%（≥87）；
`ruff check api tests` 全绿；`black --check api tests` 全绿。
