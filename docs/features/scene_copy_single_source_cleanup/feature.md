# 场景文案单一事实源与死代码清理（scene_copy_single_source_cleanup）

> 审计报告（audit-report-EchoWhale-2026-10-01.md）三项遗留清理：F17 场景文案双份漂移、
> F19 前端 mock 时代死代码、F21 会话总结死桩；外加两个快速收益小件（index.html lang、
> 首页拖拽承诺）。
> Trellis 任务：`.trellis/tasks/10-03-scene-copy-single-source-cleanup`。

## 目标

收敛三处审计确认的"漂移/死重"：

1. **F17**：场景展示文案此前由前端 sessionApi/historyApi 各维护一份 SCENE_META
   （sessionApi 版缺 `street` 键，live 会话页标题回退为原始 scene id；roleLabel 固定
   `角色 · ${role}` 裸 role id）。P2-7 之后服务端 `review_builder` 已具备单一来源基础
   （SCENE_COPY + 自然语言回退，任何路径不露原始 id），本批把它升格为唯一来源并随
   契约下发。
2. **F19**：前端 mock 时代遗留约 500 行死代码（互引无页面消费的组件、mockApi、无消费者
   hook、非流式 submitPracticeTurn），误导新读者并污染覆盖率分母。
3. **F21**：PRD v0.4 曾承诺"会话总结"，实际由 Finding 20 的 LLM 复盘承载——
   `enqueue_session_summary` 与 `SESSION_SUMMARY_PROMPT` 是零调用死桩，删除并在 PRD
   标注承载关系。

**硬约束：生产提示词零改动**——评测台以 prompt 哈希绑定基线（coach 绑
build_coach_system_prompt 实际输出、review 绑 REVIEW_PROMPT），本批不碰任何提示词文本，
评测基线不漂。

## 实现说明

### 1. F17：单一来源 = review_builder 的 get_* + contracts 的 from_* 单点消费

不新建模块：`api/modules/session_engine/review_builder.py` 已持有 `SCENE_COPY`
（coffee_shop/office/travel/street/restaurant）与 `get_scene_title` / `get_role_label`
（未命中回退"场景名 · 角色名 情景对话"式组合，`_humanize_identifier` 保证不露原始
snake_case id），contracts/history 已在消费它。本批改动：

- `api/contracts/sessions.py` `SessionResponse` 新增 `scene_title` / `role_label`
  （add-only，裸 `scene`/`role` 数据字段保留），`from_session` 是 start / reply /
  reply stream / voice bootstrap / voice complete 的唯一出口，单点取值全链路生效；
- `api/contracts/history.py` `HistorySessionMetaResponse` 同样新增两字段（detail 的
  session 元数据块与 SessionResponse 对齐）；`HistoryEntryResponse` 已有（P2-7），不动；
- review_builder.py 仅更新 41-43 行注释（"本期不被复盘卡片消费"→ 已随契约下发），
  函数与文案零改动。

前端：两份 SCENE_META 删除；`BackendSession` 增可选 `scene_title?/role_label?`；
`toSessionSummary`（sessionApi/historyApi 共同形态）优先消费后端字段，兜底走
`src/utils/humanizeIdentifier.ts`（与后端 `_humanize_identifier` 同语义，snake→空格→
逐词首字母大写，兜底同样不露原始 id）——放 utils 单份共享，避免内联两份重现双份漂移。
`PracticeSessionPage` 的 `roleLabel.replace(/^角色 · /,"")` 剥前缀消费与新字段兼容
（预设场景得到"店员对话"这类真文案，回退场景得到剥壳后的人类可读角色名）。

**liveHint 一并移除**：grep 证实 `SessionSummary.liveHint` 无任何 page/component 渲染
（仅类型定义、两个 mapper、mock 数据、测试 fixture），是随 SCENE_META 死亡的级联死
状态——从 `SessionSummary` 类型与全部 fixture 移除，不保留无消费者的字段。

### 2. F19：删除清单（删除前逐个 grep 复核，以 2026-10-03 导入图为准）

- 组件 7：`SessionStage` / `SessionMessage` / `FeedbackCard` / `SceneSummaryCard` /
  `HistoryRail` / `HistoryItem` / `UploadDropzone`（互相引用或零引用，无任何页面消费；
  `TurnFeedbackCard` 是另一个活组件，grep 子串需排除）；
- `services/mockApi.ts` + `mockApi.test.ts`（非测试代码零引用）；
- `hooks/useSpeechRecognition.ts`（零消费者零测试；`useDeepgramVoiceAgent` 是活 hook）；
- 非流式 `submitPracticeTurn`：sessionApi 导出 + practiceApi 门面（页面只用
  `submitPracticeTurnStream`；practiceApi 的 create/get 门面保留）；
  `practiceApi.test.ts` 同步移除对应用例与 mockApi spy；
- 级联孤儿：`data/mockSession.ts`（仅被死组件 type-only 引用）；`data/mockApp.ts` 仅
  `sampleScenes` 被 HomeUploadPage 消费——迁至 `data/sampleScenes.ts`（静态内容而非
  mock）后删除 mockApp.ts，`data/` 目录收口为单一静态文件。

删除后 grep 零残留（命中均为 `getHistorySessionMessages` / `TurnFeedbackCard` 一类
子串误报，已逐一人工核对）。

### 3. F21：死桩删除 + PRD 标注

- 删 `api/tasks/session_summary.py`（`enqueue_session_summary` 零调用方）与
  `api/modules/session_engine/prompts/session_prompts.py`（仅含
  `SESSION_SUMMARY_PROMPT`）；`api/tasks/` 其余成员（image_analysis / auth_mail_tasks /
  worker）与 `prompts/review_prompts.py`（REVIEW_PROMPT）保留；
- `docs/prd.md` §11 v0.4 加一行标注：会话总结由 LLM 复盘承载，见
  docs/features/teaching_kernel_prompts；只标注不改写（PRD 全面升版另行任务）；
- grep `session_summary|SESSION_SUMMARY_PROMPT|enqueue_session_summary`（api/tests/tools）
  零残留。

### 4. 与评测台遗留 #3 的关系（重要澄清）

coach_review_eval_samples/feature.md 遗留 #3 记录"`ReviewCopy.scene_title/role_label`
无生产侧硬顶，若未来随契约下发需同步补硬顶"。本批下发的展示字段来自
`get_scene_title/get_role_label` 的**确定性路径**（SCENE_COPY 预设文案或 humanize
回退），不是 LLM 产出的 `ReviewCopy.scene_title/role_label`——后者在生产链路仍然
未被消费（`build_session_review` 只消费 copy 的 highlight/next_try/next_step），原
风险面未扩大，无需硬顶。若未来把 LLM 产出直接下发，再按该遗留补消费侧硬顶。

### 5. 小件

- `frontend/index.html` `lang="en"` → `lang="zh-CN"`（界面全中文，屏幕阅读器发音口径）；
- 首页拖拽承诺兑现（选实现而非改文案）：HomeUploadPage 抽出 `handleSelectedFile` 供
  `onFileChange` 与 `onDrop` 共用（同一条 validateImage → setError/selectedFileName →
  navigate 链路），dropzone 按钮 `onDragOver` preventDefault + `onDrop` 取
  `dataTransfer.files[0]`；新增 `HomeUploadPage.test.tsx`（合法拖拽断言 navigate 与
  draft 结构、非法类型断言报错且不跳转）。

## 验证

- 后端：`uv run pytest tests --cov=api` **540 passed / 9 skipped**（基线 539/9），覆盖率
  **88.49%**（门禁 87，基线 88.44 → +0.05pt）；`uv run ruff check api tests tools`、
  `uv run black --check api tests tools` 全绿。
- 前端：`npm run typecheck` 通过；`npm run coverage` 15 文件 / 107 用例全过，覆盖率
  **Stmts 85.97 / Branch 77.42 / Funcs 84.02 / Lines 85.97** vs 阈值 76/74/78/76——
  删除未测试死代码后四项均上升，**vite.config.ts 阈值未动**（design §2.2 预判成立）。
- 提示词零改动：`git diff` 中 prompts 文本零变化（仅 session_prompts.py 整文件删除，
  本就零引用）；`review_prompts.py` 空 diff；两个 evaluation.py 空 diff；评测 fixtures
  空 diff。
- trellis-check 独立复核 10/10 PASS（验收对照、提示词零改动、add-only 契约、F19/F21
  零残留、小件读码确认、规范合规、测试质量抽查、门禁独立复跑、仓库卫生）。
- 说明：全量 pytest 不加 `MODEL_RUNTIME_MODE=mock` 进程级 pin——`tests/core/test_config.py`
  的 live 门禁测试靠自写 tmp .env 模拟 live，进程环境变量会覆盖它；回复链路测试已在
  测试内部 monkeypatch pin mock（历史基线同口径）。含 pin 的 `pytest tests/api` 已
  单独验证 88 passed。

## 遗留

- **明确排除（本批不做）**：
  - 评测台发现的 4 项提示词疑似问题（meta 黑名单误报张力、追问 ? 恰 1 过杀风险、
    ReviewCopy 标题/标签无生产侧硬顶、mock 双空分支复读原句）——已记录于
    docs/features/coach_review_eval_samples/feature.md，另批处理；
  - 前端 eslint 批次（控制面已有排期）；
  - 档案读取 API 与前端进度页（表已就绪，独立 feature）；
  - PRD 全面升版（本批只在 §11 v0.4 加标注）。
- 本批复核新发现（下批清理候选）：`types/app.ts` 的 `SampleScene.liveHint` 与
  `data/sampleScenes.ts` 中的 liveHint 数据同样零消费者——属既有死状态，不在本批
  PRD 范围，未动。
- 后端裸 `scene`/`role` 字段仍在 SessionResponse / HistorySessionMetaResponse 下发
  （add-only 契约决策，前端展示路径已不消费）；未来若做契约 v2 收敛可评估移除。
- 前端 spec 注记已同步：`.trellis/spec/frontend/` 两条"legacy mock backend 仍存在"
  表述已更新为清理后实况。
