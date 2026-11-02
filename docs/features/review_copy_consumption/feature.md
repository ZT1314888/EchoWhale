# LLM ReviewCopy 生产消费（review_copy_consumption）

> PRD v0.5 候选②：`ReviewCopy.scene_title` / `role_label` 两字段自 P2-7 起预留至今，
> 生产侧从未消费——会话与历史的展示名一直走确定性 SCENE_COPY 路径。本任务把两个字段
> 接入响应展示名（LLM 值优先、字段级回退确定性路径），让 SCENE_COPY 之外的开放集场景
> （live 视觉模型自由返回，如 gym）获得 LLM 生成的贴切展示名。完成后 PRD v0.5 四候选
> 全部交付。
> Trellis 任务：`.trellis/tasks/10-06-review-copy-consumption`。

## 目标

1. 消费优先级与回退矩阵：LLM 展示名有效（非空、≤ REVIEW_COPY_MAX_CHARS、无原始
   scene/role id 泄漏）→ 消费；否则**按字段级**回落确定性路径，不抛错；
2. 同一优先级在 reply / stream / voice 收口 / history 列表与详情 / GET 会话各消费点
   一致——全部经 `Session` 域模型单源取值；
3. REVIEW_PROMPT 补展示名子句（中文、role id 禁令、不编造），哈希重绑 + review live
   评测复跑达标（6/6 结构维度，阈值不放宽）；
4. API 契约与前端零改动（字段已在，数据源切换）。

## 设计定案（详见任务 design.md）

- **单一接缝**：所有展示名消费点都以 `Session` 域模型为唯一入参。`Session` 域模型与
  sessions 表新增 `llm_scene_title` / `llm_role_label`（可空，迁移 0014），契约构建器
  （SessionResponse / HistoryEntryResponse / HistorySessionMetaResponse 的
  `from_session`）统一改走 `review_builder.resolve_scene_title / resolve_role_label`。
- **消费矩阵**（逐字段独立判定，互不牵连）：

| LLM 值状态 | 已知场景（SCENE_COPY 命中） | 未知场景（开放集） |
| --- | --- | --- |
| None / 空白 | 确定性预设文案 | 确定性组合回退（humanize） |
| 超长（> cap 40/40） | 确定性回退 | 同左 |
| 含原始 id 变体 | 确定性回退 + `scene_display_fallback` warning | 同左 |
| 有效 | **LLM 值** | **LLM 值**（核心收益） |

- **防护校验单源**：`identifier_variants`（原始 id 下划线↔空格变体、大小写不敏感）
  从评测台迁移至 review_builder 公开导出，评测台 `_scene_or_role_id_leaks` 改 import
  ——评测与生产共享同一变体规则，杜绝双源漂移；`contains_identifier_variant` 供
  resolver 逐字段检测。
- **存原值、读侧校验**：不变量的对象是"响应路径"，所有响应都过 resolver 一处，
  写侧再校验是双源且对存量脏值无防护；泄漏值可能入库但任何响应路径都不会输出。
- **不回闪**：`save_reply_turn(review_copy=...)` 为 None（mock 模式 / 复盘降级）时不
  触碰两列，保留上一次有效值；语音收口同理（沿用 get_session 读出的既有列值）。
- **档案场景频次不动**：`learner_profile.select_display_scenes` 维持确定性
  `get_scene_title` 单参路径——档案按展示名跨会话聚合计数，LLM 每轮值不稳定会
  碎片化计数（PRD §4.8 场景键需稳定）。
- **历史条目行为收敛**：HistoryEntryResponse 此前对未知场景用单参
  `get_scene_title(scene)`（"Gym 情景对话"），统一三参后与详情/会话响应一致为
  "Gym · Fitness Coach 情景对话"（角色感知组合），有测试锁定。

## REVIEW_PROMPT 子句与哈希重绑

- Field contract：scene_title / role_label 两行追加 "must be natural Chinese; base it
  on the given scene/coach role; never output the raw role id or scene id"；
  Rules 追加 "Do not invent scenery, characters, or events beyond the given scene and
  role."（不编造画面外内容）。
- 哈希重绑：**旧 `7f82e8fef115` → 新 `4b476ab8542b`**（评测台按当前提示词自动重绑，
  JSONL 逐案绑定新哈希）。
- coach / feedback 提示词未触及（与教练评测基线绑定）。

## Live 复跑记录（2026-10-06）

环境：本地 .env live 模式，text 主槽位 SiliconFlow / DeepSeek-V3.2（未触发 failover）。
成本口径：`llm_usage` 表增量查询——复跑 6 次调用 / 3,468 prompt + 618 completion
= 4,086 tokens（复盘评测无 judge，全部入账）。

`RUN_REVIEW_EVAL=1 uv run pytest tests/modules/test_review_engine_live.py`：**1 passed
（94.8s）**，六维全达标且全部满分——structure 6/6（==1.0 硬门）、chinese 6/6、
length 6/6、no_scene_id 6/6、topic_grounding 6/6（阈值 ≥0.8 未放宽）。逐案展示名
（prompt_hash=4b476ab8542b）：

| case | scene_title / role_label | 备注 |
| --- | --- | --- |
| coffee_shop_b1_clean | 咖啡厅点单 / 咖啡师 | 已知场景 |
| office_b1_report | 办公室日常沟通 / 办公室同事 | 已知场景 |
| travel_b2_ticket | 火车站购票咨询 / 车站售票员 | 已知场景 |
| restaurant_a2_order | 餐厅点餐 / 服务员 | 已知场景 |
| gym_b1_nonpreset | 健身房 / 健身教练 | **非预设场景核心收益**：确定性回退只会给"Gym 情景对话 / 角色 · Fitness Coach" |
| coffee_shop_b2_mixed | 咖啡馆点单 / 咖啡师 | 已知场景 |

## 测试与门禁（基线只升不降）

- 新增：tests/modules/test_review_builder.py（消费矩阵 / 字段独立性 / 泄漏负向断言 /
  warning 观测 / llm=None 逐字节一致）、tests/api/test_session_display_names.py
  （三构建器同源一致性 / None 回归 / 泄漏注入负向断言）、迁移 0014 可逆性用例、
  reply/stream/voice 透传与落库保留语义用例、stream 降级轮透传 None 断言。
- 后端：`MODEL_RUNTIME_MODE=mock uv run pytest tests --cov=api` → **622 passed /
  9 skipped**（基线 596/9 净增 26），覆盖率 **89.42%**（门禁 87；同日干净基线实测
  89.34%，同口径上升）。
- ruff / black 全绿；前端 `npm run typecheck` 通过、vitest 16 文件 115 passed
  （与基线一致）、覆盖率 86.44/78.01/84.57/86.44 高于阈值 76/74/78/76；
  `git status --porcelain frontend/` 为空（前端零改动）。
- API 契约零改动：contracts 仅 `from_session` 方法体变化，无字段/类型变化。
- failure policy 不变：resolver 纯函数不抛错；复盘增强分支降级语义、CancelledError
  传播语义经 trellis-check 独立复核确认未变。

## 已知边界（记录不修）

- resolver 泄漏检测只针对**本会话**的 scene/role id（与评测台
  `_scene_or_role_id_leaks` 及 REVIEW_PROMPT 禁令同 scope）：跨场景回声（如 travel
  会话标题含 "coffee_shop"）不在防护范围——LLM 提示词已禁止，且该形态非 id 泄漏
  不变量的构成（不变量针对"本会话原始 id"）。
- 泄漏值可能入库（读侧校验架构）：任何响应路径都经 resolver，不变量在唯一出口成立；
  写侧重复校验属双源，不做。
- `docs/features/teaching_kernel_prompts/feature.md` 中"history 契约单参调用兼容"
  的表述被本批次收敛为三参角色感知，历史批次文档按惯例不改写，以本文档为准。

## PRD v0.5 四候选收口

① 档案读取 API 与进度页（learner_profile_progress）✅ ② LLM ReviewCopy 生产消费
（本批次）✅ ③ 评测驱动提示词修正（eval_prompt_fixes）✅ ④ OTel 引擎 span
（otel_engine_spans）✅ —— **四候选全部完成**，PRD §11 已同步标记。
