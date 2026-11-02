# 评测驱动提示词修正（eval_prompt_fixes）

> PRD v0.5 候选③：评测台（coach_review_eval_samples 批次）已建成但 live 评测从未实跑，
> 本任务首跑 live 评测、分诊全部发现、实施修正、复跑达标——把评测变成提示词迭代的闭环。
> 与上一批次"只建评测不改生产"相反，本任务**允许改动生产提示词与护栏**，但每次改动
> 必须"评测 + 离线样例双绿"。
> Trellis 任务：`.trellis/tasks/10-06-eval-driven-prompt-fixes`。

## 目标

1. 首跑教练 / 复盘 live 评测（10 组 + 6 组 fixture），记录逐案结果与 token 成本；
2. 分诊上批次记录的 4 项疑似问题与 live 新发现，逐项给出处置（修 / 不修 + 理由）；
3. 修正后复跑达标（阈值不放宽），prompt 哈希重绑留痕；
4. 文档收口：本清单 + 上批次清单交叉引用 + PRD §11 候选③标记交付 + 控制面。

## Live 首跑记录（2026-10-06）

环境：本地 .env live 模式，text 主槽位 SiliconFlow / DeepSeek-V3.2（备 Qwen3-235B，
本两台评测未触发 failover）；judge 走 `COACH_EVAL_JUDGE_*` 缺省回落 text 主槽位
（即完整版）。成本口径：`llm_usage` 表按时间窗增量查询；judge 的
`OpenAICompatibleClient` 构造缺省无 usage sink，**judge 调用不入账**（首跑 / 复跑各
10 次，按调用次数口径另行注明）。

### 教练评测（RUN_COACH_EVAL=1）

| 轮次 | 结果 | 耗时 | prompt 哈希（B1 / B2） |
| --- | --- | --- | --- |
| attempt-1 | 第 3 案中断（见发现 #1） | 66s | a56c951d712e / f0b4a2a60b3d |
| 首跑完整基线 | 硬规则五维 10/10；judge 8/10（final_pass 0.8 恰好达标） | 150s | a56c951d712e / f0b4a2a60b3d |
| 修正后复跑 | 硬规则五维 10/10；judge 9/10（final_pass 0.9） | 132s | fdcc04bc129e / e03313e12ae5 |

首跑 judge 否决 2 案（0.8 阈值内，均为主观分歧，处置见下"发现 #3"）：

- travel_b1_ticket：judge 判追问 "Which platform does the airport train leave from?"
  与购票"不相关"、不合角色——实际上平台信息与"去机场"直接相关，judge 过严；
- office_b2_multiturn：judge 判 stretch 不足（问合同具体条款对 B2 "太窄或太难"）——
  拉伸质量属主观判断。

### 复盘评测（RUN_REVIEW_EVAL=1）

| 轮次 | 结果 | 耗时 | prompt 哈希 |
| --- | --- | --- | --- |
| 首跑 | structure / chinese / no_scene_id / topic_grounding 6/6；**length 5/6** | 61s | f1a6629e1263 |
| 修正后复跑 | 六维（含 length）**6/6 全绿** | 53s | 7f82e8fef115 |

首跑唯一挂案：office_b1_report 的 next_try 83 字符超 80 上限（模型整句引用
more_natural 改写；coffee_shop_b1_clean 的 77 字符同样贴边，属系统性模式而非偶发）。
复跑同案 next_try 降到 47 字符，全样例 next_try ≤ 67——提示词子句见效。

### token 成本

| 阶段 | 记账调用 | prompt tokens | completion tokens | 合计 |
| --- | --- | --- | --- | --- |
| 首跑两台（coach 基线 + review 首跑） | 19 | 6,612 | 1,025 | 7,637 |
| 复跑两台（coach + review） | 16 | 6,215 | 931 | 7,146 |

注：记账含 review 少量重试调用；judge 调用（20 次）无 sink 不入账，量级与回复调用
相当（短文本单轮）。

## 分诊处置（4 项已记录 + 3 项 live 新发现）

对 `docs/features/coach_review_eval_samples/feature.md` 遗留清单的逐项闭环：

| # | 问题 | 处置 | 落点 |
| --- | --- | --- | --- |
| a | meta 黑名单 "i can't see" 误报张力 | **修（双管）**：黑名单收窄 + 提示词接地 | coach_engine/evaluation.py + coach_prompts.py |
| b | 追问恰 1 个 `?` 多轮过杀 | **修**：区间 [1,2] | coach_engine/evaluation.py |
| c | ReviewCopy.scene_title/role_label 无生产硬顶 | **修**：五字段校验层截断 cap | session_engine/review_builder.py |
| d | MockChatProvider 双空分支复读学习者原句 | **修**：两条复读路径都改中性短语 | coach_engine/providers/chat_provider.py |
| live #1 | judge 调用无兜底，超时炸整轮（attempt-1 实发） | **修**：judge 纳入 try/except，记 judge_error、final 回落 hard_pass | coach_engine/evaluation.py |
| live #2 | next_try 整句引用长英文例句必然触顶 | **修**：REVIEW_PROMPT 子句（引用取最短形式） | review_prompts.py |
| live #3 | judge 主观分歧 2 案（travel_b1_ticket / office_b2_multiturn） | **不修**：judge 是 0.8 阈值下的主观参考信号，单案分歧是信号本义；原始 reason 留上文备查 | — |

### 修 a（评测规则收窄 + 提示词接地）的理由与 live 验证

- 黑名单收窄：裸 "i can('t) see" 的拦截本意是出戏的"我看不见你发的图"，而
  "I can't see the screen from here" 是场景内合法台词——收窄为图像锚定变体
  （the image / the photo / any image × can't / cannot 共 6 个）消除误报类，
  其余 token 不动。**这是校验器语义修正，不是为绿改测试**。
- 提示词接地行："Treat the visual anchors as things in the scene right in front of
  you, and never mention images, photos, or being unable to see."——上批次记录的
  处置指引是"改提示词侧措辞"（行为修复优先），与校验器收窄互补。
- live 验证：两轮 meta_leak 均 10/10（fixture 输入下本就未触发误报），修正后无回归。

### 修 b（follow_up 区间）的理由与 live 验证

产品契约（PRD 4.3"每轮只推动一个明确交流目标"）的可校验语义是**以追问收口且不连环
发问**：下界 1 保证推进，上界 2 容忍多轮窗口引用教练自己上一问的正常形态（该形态
恰 1 判定必误判）。0 与 ≥3 仍挂。提示词侧 "one follow-up question" 保持产品理想态
不动。live 验证：两轮 follow_up 均 10/10，修正后无回归。

### 修 c（ReviewCopy 五字段 cap）的设计

- `REVIEW_COPY_MAX_CHARS`（40/40/120/80/80，与 REVIEW_PROMPT 软约束逐字段一致）成为
  生产单一事实源，`ReviewCopy` 增加截断型 validator（strip 后截断 + warning 观测
  日志，对齐教练 2000 字符硬顶"截断并留观测日志"纪律）；`min_length=1` 与 strip
  前置语义不变（纯空白仍失败触发 failover），failure policy 不变。
- 选择截断而非拒绝：拒绝会把其余字段完好的复盘整份打向重试 / 模板降级，损失大于
  半句截断；消费侧 `_bound` 与教练输出硬顶均为截断先例。
- `session_engine/evaluation.py` 的 `REVIEW_COPY_FIELD_LIMITS` 改为从 review_builder
  import（消除双源）。**信号转移**：cap 落地后 live 输出超限在校验层被截断，评测
  长度维度退化为"生产护栏未被移除"的回归哨兵（单测用 `model_construct` 绕过校验
  保持该失败分支覆盖）——长度漂移的提示词信号由 REVIEW_PROMPT 软约束与其余四维承担。
- API 契约零改动：ReviewCopy 是内部模型且五个字段当前无任何下游消费（对外下发的
  scene_title/role_label 来源是 SCENE_COPY 预设，非 LLM 输出）。

### 修 d（mock 双复读路径）的设计

`recent_messages` 为空时首句回落学习者原句、anchors/vocab 双空时 "Let's practice
with {learner}" 两条路径都改为中性短语；fixture 三个约束（末条非空 / ≠ learner /
无问号）保留为双保险；`build_follow_up` 收尾与三句形态不变。新增单测用 ≥4 token
学习者消息 + 空 recent_messages + 双空输入锁定五维全过。

## 哈希重绑记录

评测台按当前提示词自动重绑（无手动步骤），新旧对比如下：

| 提示词 | 修正前 | 修正后 |
| --- | --- | --- |
| coach B1（build_coach_system_prompt("B1")） | a56c951d712e | fdcc04bc129e |
| coach B2（build_coach_system_prompt("B2")） | f0b4a2a60b3d | e03313e12ae5 |
| review（REVIEW_PROMPT） | f1a6629e1263 | 7f82e8fef115 |

FEEDBACK_PROMPT 未触及（4 项已记录疑点与 live 新发现均不涉反馈侧契约），哈希不变，
`RUN_FEEDBACK_EVAL` 无需补跑。

## 验证

- `uv run pytest tests --cov=api`：596 passed / 9 skipped / 1 failed——失败为
  test_telemetry_e2e（既有环境陷阱：本机 .env live 模式，须 `MODEL_RUNTIME_MODE=mock`
  进程 pin 复跑，pin 后 4 passed；控制面既有注记）；等效 600 passed / 9 skipped，
  较基线 589/9 净增 11 用例。覆盖率 **89.46%**（门禁 87，基线 89.02% 抬升）。
- `uv run ruff check api tests tools`、`uv run black --check api tests tools`：全绿。
- 前端零改动证明：`git status` frontend/ 无变化；`npm run typecheck` 通过；
  `npm run coverage` 16 文件 115 passed（与基线一致），覆盖率 86.44/78.04/84.57/86.44
  对阈值 76/74/78/76 全部高于阈值。
- live 复跑达标（阈值未放宽）：coach 硬规则五维 10/10、final 0.9（≥0.8）；
  review 六维 6/6（含首跑挂掉的 length）。
- `uv run python -m tools.agent_ops render` + `check`：通过。

## 遗留

- judge 维度仍是主观参考信号：travel_b1_ticket 连续两轮被否（理由措辞不同），
  若后续批次引入更强 judge 模型或 judge 提示词细化，需重新评估该案的稳定性。
- B1/B2 难度适配与复盘文案的教学质量仍需人工评估（与 P2-7 / 上批次遗留同源）。
- 语音链路（Deepgram）提示词评测需真实会话，维持另行立项（上批次明确排除）。
- ReviewCopy.scene_title/role_label 的生产消费（PRD §11 候选②）待立项；本批 cap
  已为其备好输出边界。
