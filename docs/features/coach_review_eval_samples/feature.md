# 教练与复盘离线评测样例集补全（coach_review_eval_samples）

> 审计 Schedule Later 第 18 项"反馈/教练离线评测样例集（复用场景评测台）"的教练与复盘两侧
> （反馈侧已由 teaching_kernel_prompts 批次补齐）。
> Trellis 任务：`.trellis/tasks/10-03-coach-review-eval-samples`。

## 目标

教学内核（提示词 + 动态学员档案）是最核心的产品资产，但教练与复盘的提示词/公式改动此前是"盲飞"——只有反馈引擎有离线评测、场景引擎有 live 评测台。本任务为教练（coach_engine 提示词链路）与复盘（ReviewSummarizerAgent LLM 复盘）建立离线回归评测：固定输入样例集 + 硬规则校验器（always-on 单测复用）+ 教练可选 LLM judge + `RUN_COACH_EVAL=1` / `RUN_REVIEW_EVAL=1` 门控 live 评测 + JSONL 结果落盘与 prompt 哈希绑定。**生产代码零改动**——只建评测，不改任何提示词。

## 实现说明

### 1. 规划定案：按引擎各建模块，不抽共享泛化骨架

以 prd 给出的双判据（scene 现有实现不被破坏、总代码量更小）核对：抽公共层的显著收益
来自把 scene 评测台改造成调用公共层——必然修改现有文件，与"生产代码零改动"冲突；
scene 保持自有实现时公共层对 scene 零收益。可真正共享的代码只有 prompt 哈希（3 行）、
JSONL 落盘（5 行）、judge 工厂（约 30 行），泛化层需 100+ 行抽象去省约 40 行重复，
净增代码量。定案：模式同构、代码独立；唯一跨引擎复用是思路复用（meta 黑名单在
coach 侧自持扩展副本并注明来源，不做跨引擎 import）。硬规则校验器的双通道复用在
模块内部解决：公开纯函数被 always-on 单测与 gated live 评测 import 同一实现。

### 2. 评测台（新增 2 个模块，零修改现有文件）

- `api/modules/coach_engine/evaluation.py`：`CoachReplyEvaluationCase`（scene/role/
  anchors/vocab/recent_messages/learner_message/learner_cefr/learner_context）→
  `evaluate_coach_reply_hard_checks` 五维硬规则纯函数（仅输出英语：CJK/谚文/假名字符
  检测；长度 ≤80 词；`?` 恰好 1 次即"恰好包含追问"；meta 泄漏黑名单——场景台
  META_OPENER_TOKENS 思路的扩展副本，另加 "as a language model"、"i (am|'m) an ai"、
  "i can('t|not) see"（教练无图可看，比场景台更严）；不复读学习者原句：规范化 token
  连续子序列匹配，<4 token 短应答豁免防误报）→ `evaluate_coach_reply` 折叠
  （graceful_failure 分支、judge 结果注入）→ `build_coach_prompt_hash`（sha256 前 12 位，
  **绑定每组实际发送的系统提示词** `build_coach_system_prompt(case.learner_cefr)` 输出，
  B1/B2 天然异哈希，模板或注入值任一变化都可归因）→ 可选 `CoachReplyJudge`（与
  SceneOutputJudge 同构：strict JSON 的 final_pass + role_fit/cefr_fit/stretch 三维度 +
  reason，`COACH_EVAL_JUDGE_*` 环境变量缺省回落 text 槽位）→ `run_coach_evaluation`
  顺序 runner（8-10 案单次文本调用，无需 scene 台的并发限流）。
- `api/modules/session_engine/evaluation.py`：`ReviewEvaluationCase`（feedback 直接复用
  `FeedbackResult` 全字段）→ `evaluate_review_copy` 五维硬规则（结构五键经真实链路
  校验；五字段 CJK 中文；40/40/120/80/80 与 REVIEW_PROMPT 软约束逐字段一致——消费侧
  `_bound` 硬顶只覆盖三字段，评测在源头卡全五个；无原始 scene id/role id 含下划线↔空格
  变体、大小写不敏感；"不编造"用**无关话题关键词黑名单**做确定性代理断言——正向词面
  重叠跨语言不可靠，黑名单代理的局限已在注释说明）→ `build_review_prompt_hash()`
  绑定 `REVIEW_PROMPT` → `run_review_evaluation` 走真实 `ReviewSummarizerAgent.summarize()`
  （含 parse_llm_json + failover 路径）。

### 3. fixtures（提交入库，两通道共用）

合成文本样例无真实图片 URL 依赖，直接入库（scene 台样例需 signed URL 所以只在 tmp/）：
`tests/fixtures/coach_eval_cases.json` 10 组（coffee_shop/office/restaurant/travel 4 场景 ×
B1×5 + B2×5；含 learner_context 注入块 B1/B2 各 1 组、≥4 条多轮 2 组、anchors/vocab
双空回退分支 1 组）；`tests/fixtures/review_eval_cases.json` 6 组（4 预设场景 + gym
非预设——专测"不得把原始 id 当标题"的回退路径；≥2 组含 errors + cefr_level，9 类封闭
分类全取样）。约束由载入测试锁定：教练每组 recent_messages 末条非空、≠ learner_message、
不含 `?`（mock 回复引用末条消息，该约束是 always-on mock 通道全绿的前提）；复盘黑名单
词与 SCENE_COPY 预设文案零撞车（防 live 误报）。

### 4. 测试双通道与门控

- **always-on**（CI 必跑，26 个新用例）：`test_coach_evaluation.py`（15 个：五维正反直测、
  折叠 graceful_failure/judge 注入、哈希稳定/敏感、fixture 载入契约、**mock 输出全样例
  通道**——显式 `monkeypatch` pin `MODEL_RUNTIME_MODE=mock` 后对 fixture 全部案例经
  `MockChatProvider` 跑硬规则；本地 .env 是 live 模式，不 pin 会打真 LLM）；`test_review_evaluation.py`
  （11 个：五维正反直测、哈希、载入契约、折叠分支）。
- **gated live**（CI 默认 skip，零费用）：`test_coach_engine_live.py`（`RUN_COACH_EVAL=1`）
  与 `test_review_engine_live.py`（`RUN_REVIEW_EVAL=1`），pytestmark skipif 沿 scene 先例；
  进入即断言 `MODEL_RUNTIME_MODE=live` 否则 fail（mock 产物过不了硬规则会误导回归结论，
  沿 feedback 先例）；`COACH_EVAL_CASES_FILE` / `REVIEW_EVAL_CASES_FILE` 缺省回落入库
  fixtures，结果落 `COACH_EVAL_OUTPUT`（tmp/coach_engine_eval/results.jsonl）与
  `REVIEW_EVAL_OUTPUT`（tmp/review_engine_eval/results.jsonl）；通过率断言：coach
  english_only/meta_leak == 1.0（绝对回归项）、hard/final ≥ 0.8；review structure == 1.0
  （failover 保证）、余四维 ≥ 0.8。live 测试未实际执行（产生费用），正确性由折叠函数
  单测与 scene/feedback 台同构性保证。

## 验证

- `uv run pytest tests --cov=api`：539 passed / 9 skipped（基线 513/7 + 26 always-on
  + 2 gated skip），覆盖率 88.44%（门禁 87，基线 88.76，-0.32pt 在缓冲内）；未使用
  任何 `# pragma: no cover`（live-only runner/judge 靠缓冲覆盖，模块单测覆盖率
  coach 79% / review 86%）；全量 33s 无网络长尾。
- `uv run ruff check api tests tools`、`uv run black --check api tests tools`：全绿。
- `git diff --name-only` 为空：无任何 tracked 文件被修改（含 pyproject/.env.example），
  api/ 侧仅两个新增 evaluation.py。
- `uv run python -m tools.agent_ops render` + `check`：通过。
- trellis-check 独立复核 9 项全 PASS（生产零改动、门禁复跑、CI 零费用、always-on
  无网络、design 定案执行、prd 验收对照、代码质量、fixture 约束、仓库卫生）。

## 遗留

- **明确排除**：语音链路（Deepgram）提示词评测需真实会话，另行立项，不在本任务范围。
- 教练 live 评测未实跑（费用与真实 provider 依赖）：首次实跑命令
  `RUN_COACH_EVAL=1 uv run pytest tests/modules/test_coach_engine_live.py`（可先配
  `COACH_EVAL_JUDGE_*` 启用裁判）；复盘同理 `RUN_REVIEW_EVAL=1`。
- 评测暴露的提示词疑似问题清单（**只记录不改**，留给后续提示词批次裁量）：
  1. meta 黑名单 "i cannot see / i can't see" 与教练现实存在张力——教练的视觉锚点是
     文本线索，live 模型诚实回答 "I can't see the photo, but from the menu board..."
     会被判反；首次实跑观察 meta_leak 是否 1.0，若误报应改提示词侧措辞而非放宽校验器。
  2. `?` 恰好 1 次的追问判定在真实对话存在过杀风险——recent_messages 末条若是教练
     自己的问句，回复引用它会计 2 个 `?`；fixture 用"末条无问号"约束规避了 mock
     通道，live 真实对话无此约束。
  3. `ReviewCopy.scene_title/role_label` 无生产侧硬顶——消费侧 `_bound` 只截三个字段，
     40/40 上限与"禁原始 id"目前只有本评测台在守；若未来随 history 契约下发需同步补
     消费侧硬顶。
  4. `MockChatProvider` 在 anchors/vocab 双空回退分支复读学习者原句（"Let's practice
     with {learner}"），≥4 token 的真实消息在该分支会挂 no_echo——mock 质量瑕疵
     （非生产链路），fixture 已用短消息绕开，备忘。
- 教练 live 评测的 B1/B2 难度适配主观质量仍需人工评估（与 P2-7 遗留同源）。
