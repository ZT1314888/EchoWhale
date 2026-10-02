# 学员状态持久化与提示词动态注入（learner_profile_prompt_injection）

> 审计对标结论 10（P2-7，与 Speak proficiency graph / Duolingo Max 对标的核心差距项）。
> Trellis 任务：`.trellis/tasks/10-02-learner-profile-prompt-injection`。

## 目标

兑现 teaching_kernel_prompts 批次预留的 `COACH_LEARNER_LEVEL` 注入位：为认证用户持久化学习档案（每用户一行），从每轮 `FeedbackResult` 已产出的信号（9 类封闭错误分类 + CEFR 估计）零额外 LLM 成本地滚动累积学员状态，并把状态动态注入教练 / 反馈 / 语音三处提示词，让教练随练习轮次逼近学员真实水平；无档案时回退静态中级占位，前端与 API 契约零改动。

## 实现说明

### 1. 数据模型（迁移 0013）

- 新表 `user_learning_profiles`（`api/db/learner_profile_db.py`，async 域 Protocol + SqlAlchemy 实现 + 工厂三件套）：`user_id` PK（存 owner 全串 `user:<id>`，与 `sessions.user_id` 同一身份约定，无 FK 与会话表惯例一致）、`cefr_estimate`（A1..C2 可空）、`error_type_counts` JSON（仅 9 类封闭集合键）、`scene_counts` JSON（**写侧封顶 12**，插入序 = 近期序）、`cefr_history` JSON（封顶 10）、`practiced_turn_count`、时间戳。迁移 `20261002_0013` 挂 0012 之后，upgrade/downgrade 可逆对，已在本地 PG 实测往返。
- **访客显式排除**（design.md 1.2 定案）：`visitor:*` 会话零读写档案——访客身份是可轮换的签名 cookie，键无界增长且无合并/清理语义，建档价值为零；注册后产生的新会话才归属 `user:`，历史访客会话不回填。读侧零查询 + 写侧零写入，测试 `test_reply_skips_learner_profile_for_visitor_owner` 锁定读写双零。

### 2. 更新路径（零额外 LLM 调用）

- 纯函数 `apply_turn_to_profile`（`api/modules/session_engine/learner_profile.py`）：错误分类只累加 9 类封闭集合内的 category（schema 不校验 category，模型幻觉值在此防御性丢弃）；场景计数 pop + 重插尾部（"最近使用"移到末尾）超上限从头淘汰最旧；轮数自增。
- **CEFR 滚动估计定案：median_low，否决 EWMA**。A1..C2 → 1..6 序数，`cefr_history` 封顶 10 淘汰最旧，`cefr_estimate = LEVELS[median_low(ordinals) - 1]`——偶数窗口取下中位，结果恒为已观测级别（无分数级别、无浮点）。否决 EWMA 的理由：估计需写回 6 级封闭集合，EWMA 连续值必须再取整（相邻级别间震荡/粘滞）且 alpha 是无依据超参；median_low 免超参、对单轮异常估计稳健、可解释（"最近 10 轮的中位水平"）。
- 编排接线（`session_engine/agent.py`）：reply 在 `save_reply_turn` 成功后、stream 在 `yield ("session", ...)` 前（即落库后）、语音在 `finalize_voice_session` 成功后更新；与消息落库**不同事务不同连接**，profile 写失败可独立回滚。更新是增强分支：`except Exception` → `learner_profile_update_failed degraded=true` warning，本轮照常成功；不吞 CancelledError（断连语义不变）。
- mock 一致性：mock 反馈 `cefr_level=None` → CEFR 估计不动，但场景/轮数照常累计（测试锁定）；visitor 门控使 visitor 路径零开销。
- 已知取舍（design.md 2.3）：同用户并发轮的 read-modify-write 非原子，最坏丢一次计数（last-write-wins）——档案是估算用途、单用户并发轮罕见，不值得为其上 `FOR UPDATE` 并牺牲 SQLite 测试兼容。

### 3. 三处注入（注入面不扩大）

- 渲染 `build_learner_context_lines`：CEFR 行 + top ≤3 错误类别行（count 降序、名称升序决胜）+ 轮数行；全部是封闭集合值/整数、服务端拼装，**绝不注入学习者原文与场景名**（守卫测试锁定）。
- 教练：`coach_prompts.py` 抽出 `build_coach_system_prompt(learner_cefr=None)`，动态 CEFR 覆盖水平行；`COACH_LEARNER_LEVEL` 降级为回退默认值，`COACH_SYSTEM_PROMPT = build_coach_system_prompt(None)` 与旧常量**逐字节一致**（独立脚本对比 + 测试双锁定）。`CoachReplyInput` 新增 `learner_context` / `learner_cefr` 可选字段，live provider 动态构建系统提示词，`_build_coach_user_prompt` 有 context 追加块；mock provider 不读系统提示词，行为不变。
- 反馈：`FeedbackInput.learner_context` 可选，live user_prompt 追加注入行；mock 路径输出不变。
- 语音：`build_voice_agent_prompt(session, learner_context=None)` 与 `DeepgramSettingsBuilder.build(session, learner_context=None)`（`VoiceSettingsBuilder` Protocol 同步增可选参数），注入块插在对话历史前；bootstrap 时点查档案渲染。
- 回退语义：无档案 / 点查失败 / 字段缺失 → 三处全部回退现状（静态 B1 / 无注入块），点查失败记 `learner_profile_load_failed degraded=true` warning。

### 4. 配置

- `learner_profile_scene_cap=12`（场景封顶，防视觉模型自由产出场景名的无界增长）、`learner_profile_cefr_window=10`（CEFR 滚动窗口）；`.env.example` 同步；均带默认值、非启动关键项，不进 `validate_runtime()` 生产清单（档案缺失自动回退静态注入）。

### 5. 连带修复（迁移 0004）

- `tests/db/test_session_write_integrity.py` 的两个迁移可逆测试在**干净基线即红**（stash 实验证实）：alembic 1.18.4 不再在 SQLite 上自动 batch `op.alter_column`（`ALTER TABLE ... ALTER COLUMN` 语法错）。按迁移 0011 同款 `batch_alter_table` 模式修复 0004；PG 下 batch 是普通 DDL，行为不变。

## 验证

- `uv run pytest tests --cov=api`：513 passed / 7 skipped，覆盖率 88.76%（门禁 87，基线 88.36），全量 16.8s 无 live 调用。
- `uv run ruff check api tests tools`、`uv run black --check api tests tools`：全绿。
- 迁移：本地 PG `upgrade head → downgrade -1 → upgrade head` 往返成功；0004 连带修复后 `test_session_write_integrity` 9 passed。
- trellis-check 独立复核 10 项全 PASS（门禁复跑、failure policy、访客排除、注入面、更新数学、数据层、0004 基线红实验证实、契约零破坏、测试质量、仓库卫生）。
- 新增测试 36 个：仓储往返（aiosqlite 真仓储）、更新数学（幻觉 category / 封顶淘汰 / median_low 奇偶窗口 / None 不动）、注入渲染与守卫、编排接线（user 落档 / visitor 双零 / 仓储失败降级 / payload 携带 context）、三处 prompt 有无注入两形态。触改 reply/stream/voice 测试全部显式 pin mock。

## 遗留

- 档案只写不读 API：前端暂无"学习进度"页面，`GET` 档案端点与前端消费是后续 feature（表结构已就绪）。
- 注入效果的主观质量（教练难度适配是否可感知）需上线后人工评估；`learner_profile_update_failed` 频率应≈0（纯本地 DB 写），异常升高优先查 DB 连接池。
- 并发丢计数取舍如需收紧，可在 PG 侧换 `INSERT ... ON CONFLICT` 带增量 SQL 或行锁（当前不值得）。
- 环境事件记录：2026-10-02 Windows 智能应用控制（SAC）评估期结束转开启，拦截 uv 托管 CPython 3.14 解释器（os error 4551 / Permission denied）；项目 `.venv` 已重建到 python.org 签名的系统解释器 `C:\Program Files\Python314\python.exe`（`uv venv --python ... --clear && uv sync`），SAC 无单应用白名单，若需恢复 uv 托管解释器只能关闭 SAC（不可逆）或改用未拦截的解释器。
