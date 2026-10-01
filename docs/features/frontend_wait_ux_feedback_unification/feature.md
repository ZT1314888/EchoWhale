# Feature: `frontend_wait_ux_feedback_unification`

## 基本信息

- `feature`: `frontend_wait_ux_feedback_unification`
- `status`: `feature_test_passed`
- `module`: `frontend_app`
- `cross_module`: `no`（纯前端；消费既有 202 轮询与 SSE 契约）
- `owner`: `lucky`
- `updated_at`: `2026-09-30`
- `merge_target`: `module/frontend_app`

## 背景

202 轮询接线后仍有两个体验毛边：上传等待页的三段进度是固定 1.1s 假计时，60 秒真实分析期间「准备完成」灯早已点亮，且用户被钉死在加载页没有退出通道；练习页的回合反馈只有文字路径的悬浮卡，落库后悬浮卡与消息脱节，两条入口的反馈呈现不一致。

## 用户故事

- 当我的图片在排队做场景分析，我希望进度反映真实状态，并且随时可以取消等待返回首页。
- 当一轮文字练习完成落库，我希望反馈直接挂在那条消息上，而不是一张与对话流脱节的悬浮卡。

## 范围

### In scope

- `waitForSceneAnalysis` 支持取消：`AbortSignal` 贯穿轮询（可中断 sleep + 轮询前后检查 + in-flight 状态请求取消时原样上抛 `AbortError`）；新增 `onStatus` 逐次回调
- `sessionApi.createSession/createPracticeSession/createSamplePracticeSession` 接受可选 `signal`；`AbortError` 原样透传（不再被吞成 SESSION_START_FAILED）
- `practiceApi.createPracticeSession` options 增加 `signal` / `onAnalysisStatus` 并透传给轮询与重试 POST
- `StartupLoadingPage`：分析等待期间进度锁在「角色」档（`ANALYSIS_HOLD_STAGE`）直到轮询真实 ready；新增「取消等待」按钮（abort + 返回首页）；卸载时自动 abort 在途轮询
- `TurnFeedbackCard` 增加 `compact` 变体（`data-testid="message-feedback-card"`，无标题，紧凑样式）
- `PracticeSessionPage`：落库消息自带 feedback 时内联渲染 compact 卡（挂在带 feedback 的消息下）；文字回合 resolve 后清理悬浮卡，由内联卡接棒
- `PracticeMessage` 类型增加可选 `feedback`；`toPracticeMessage` 映射后端逐条 feedback

### Out of scope

- 语音实时逐轮反馈（后端 voice/complete 只产出聚合 review，不落逐条消息 feedback——经源码确认；文档化边界，待语音管线改造）
- 加载页内联分析路径（非 202）的进度真实化
- 历史回放页的逐条 feedback 呈现

## 设计要点

- 取消语义：sleep 可被 abort 提前唤醒，轮询请求带 signal；单次轮询失败的 catch 先检查 `signal.aborted` 再决定 continue，避免把取消吞成网络抖动
- 悬浮卡生命周期收窄：`turnFeedback` 只覆盖「已发未落库」窗口（feedback 事件先现 → delta 流式 → done 帧），resolve 后由消息自带 feedback 的内联卡接棒，无重复展示
- 逐条 feedback 挂在后端返回的对应消息上（文字回复路径实测挂在教练消息），渲染与数据同源、角色无关

## 测试

- `TurnFeedbackCard.test.tsx`：live 卡带标题、compact 卡无标题且 testid 区分
- `PracticeSessionPage.test.tsx`：流式三段（live 卡先现 → delta 逐字 → 落库后内联卡 ×1 且悬浮卡退场）、失败保留草稿、取消清理（本批补上第四批补丁崩溃时丢失的三个页面级用例，断言按内联行为更新）
- `mediaApi.test.ts`：signal 在下一次轮询前中止（fetch 零调用）、in-flight 状态请求被取消时原样上抛
- `practiceApi.test.ts`：signal/onStatus 透传 + AbortError 冒泡
- `App.test.tsx`：分析等待中点「取消等待」返回首页
