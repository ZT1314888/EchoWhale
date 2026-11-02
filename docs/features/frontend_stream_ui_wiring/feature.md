# Feature: `frontend_stream_ui_wiring`

## 基本信息

- `feature`: `frontend_stream_ui_wiring`
- `status`: `feature_test_passed`
- `module`: `frontend_app`
- `cross_module`: `yes`（消费 session_orchestration 的 SSE 端点与 scene_engine 的状态端点）
- `owner`: `lucky`
- `updated_at`: `2026-09-30`
- `merge_target`: `module/frontend_app`

## 背景

第三批已交付 SSE 端点与 202 + 状态轮询的后端能力，但页面未接线：练习页仍是纯语音流，POST /sessions 的 202 挂起载荷会被前端当成功解析出空 sessionId。学习者既用不上逐字流式回复，也无法在异步分析期间得到等待反馈。

## 用户故事

- 当我发出一条文字练习消息，我希望先看到反馈卡片、再看着教练回复逐字出现，这样不用盯着空白等待整段生成。
- 当分析排队或网络中断，我希望页面明确显示"分析中"并能取消/重试，而不是拿到一个静默的空会话。

## 范围

### In scope

- `TextComposer` 组件：textarea（Enter 发送 / Shift+Enter 换行）、发送/取消按钮切换、发送中禁用输入、AbortSignal 取消、失败与取消保留草稿
- `TurnFeedbackCard` 组件：渲染 `PracticeFeedback`（Grammar / More Natural / Useful Words / Next Step 四格）
- `PracticeSessionPage` 接线 `submitPracticeTurnStream`：线程内按「learner 实时气泡 → 反馈卡 → coach 流式气泡」渲染（对齐后端 feedback → delta* → session 事件序），done 帧全量刷新 `session.messages`；发送中禁用语音按钮、状态胶囊显示 Thinking；AbortError 静默清理、业务错误走既有 inline error 透出
- `mediaApi.getSceneAnalysisStatus`：状态端点载荷映射；`waitForSceneAnalysis`：2s 间隔 / 60s 总超时轮询，单次失败容忍继续；1007 → `UNSUPPORTED_SCENE_IMAGE`、其余 → `SCENE_ANALYSIS_FAILED`、超时 → `SCENE_ANALYSIS_TIMEOUT`
- `sessionApi.createPracticeSession` 返回类型收窄为判别联合 `SessionStartOutcome`（created | analyzing，202 不再解析成空 sessionId）
- `practiceApi.createPracticeSession(draft, { onAnalysisPending })`：编排 202 → 轮询 → 重试（最多 3 次），页面只接 `onAnalysisPending` 回调
- `StartupLoadingPage`：分析排队文案、按钮切换"正在分析场景…"、failed/超时给「重试创建练习 + 换一张图片」双动作

### Out of scope

- 语音链路流式化与语音回合的反馈卡片
- 会话页消息区的整体重构（沿用现有 session-thread 渲染）
- 后端任何改动（SCENE_ANALYSIS_ASYNC_ENABLED 维持默认关闭）

## 设计要点

- 关键流程：TextComposer.onSend(content, {signal}) → 页面 onSendText → submitPracticeTurnStream(sessionId, input, handlers, signal) → onFeedback/onDelta setState → Promise resolve 后以 SubmitPracticeTurnResult 整体替换 messages
- 失败原子性依赖后端：任一分支失败整轮不落库，前端保留流式残影与草稿即可安全重发
- 202 编排放服务层（practiceApi）而非页面，轮询常量与错误映射收敛在 mediaApi，组件测试只覆盖状态展示
- 依赖模块：`session_orchestration`（SSE 契约与事件序）、`scene_engine`（状态端点与 1007 语义）

## 契约

- `SessionStartOutcome = { kind: "created"; sessionId } | { kind: "analyzing"; mediaId }`
- 状态载荷：`{ media_id, status: unknown|pending|ready|failed, prompt_version?, scene?, role?, confidence?, error_code? }`
- 轮询常量：`SCENE_ANALYSIS_POLL_INTERVAL_MS = 2000`、`SCENE_ANALYSIS_POLL_TIMEOUT_MS = 60000`

## 测试

- `frontend/src/components/TextComposer.test.tsx`：成功清空、发送中禁用 + 取消、失败留稿、空内容不发送
- `frontend/src/pages/PracticeSessionPage.test.tsx`：流式三段渲染次序、结构化错误透出 + 草稿保留、取消清理
- `frontend/src/services/practiceApi.test.ts`：202 → 轮询 → 重试建会话、failed 透传
- `frontend/src/services/mediaApi.test.ts`：载荷映射、ready 轮询、1007 映射、超时（fake timers）
- `frontend/src/services/sessionApi.test.ts`：202 pending 载荷判别
- `frontend/src/App.test.tsx`：异步分析等待后进入会话、failed 双动作；会话页文字输入存在性断言（反转上一批的"不出现"钉死）
