# 反馈失败降级不拖垮整轮对话（feedback_failure_degradation）

> 审计报告（audit-report-EchoWhale-2026-10-01.md）Finding 6 修复。
> Trellis 任务：`.trellis/tasks/10-01-feedback-failure-degradation`。

## 目标

`SessionEngineAgent.reply()` / `stream_reply()` 中反馈与教练并发后，原逻辑"任一分支失败即整轮上抛"——反馈 provider 故障窗口内用户一次都练不了，教练回复即使已完整生成也被丢弃。本特性确立编排器失败策略：**主价值分支（教练）失败才整轮失败，增强分支（反馈）失败必须显式降级**。

## 实现说明

- `_resolve_feedback(result)` / `_degraded_feedback_with_log(exc)` / `_degraded_feedback()` 三个助手构成唯一降级转换点：反馈失败 → warning 日志（`session_reply_branch_failed` 事件名 + `degraded=true branch=feedback`）→ 占位 `FeedbackResult`（每次新建实例，文案诚实标注"本轮反馈生成失败……下一轮照常返回"）。
- `reply()`：feedback 失败降级；coach 失败以原异常类型上抛（两分支都失败时降级日志与 coach 异常都不丢失）。`_unwrap_gather_results` / `_log_failed_branch` 删除。
- `stream_reply()`：`await feedback_task` 包 `except Exception`（CancelledError 等 BaseException 原样传播，取消语义不变）；coach 流打不开的早退路径（cancel 反馈任务 → raise）原样保留。SSE 事件序 `feedback → delta* → session` 不变，降级时 feedback 事件载荷为占位反馈。
- 占位反馈同时流入 `Message.feedback` 与 `build_session_review`——契约模型与前端零改动，反馈卡片与复盘自然渲染占位文案。
- 范围外（保持现状）：`complete_voice_session` 直接 await 反馈，失败仍整轮失败（语音收口语义独立，留待后续批次统一降级策略）。

## 验证

- 语义翻转：`test_stream_reply_aborts_without_persisting_when_feedback_fails` → `test_stream_reply_degrades_feedback_and_persists_when_feedback_fails`（事件序完整、saved_turns==1、占位落库、caplog 断言）；新增非流式 `test_reply_degrades_feedback_and_persists_when_feedback_fails`。
- 教练三类失败用例（open 失败 / 中途断流 / 空输出）断言零改动全绿。
- `uv run pytest tests -q`：388 passed / 2 skipped；ruff / black 全绿；mock 模式 uvicorn 冒烟 /health 200。

## 遗留

- `complete_voice_session` 的反馈降级对齐（语音收口路径）。
- 反馈异步补写（失败后事后回填已落库消息）涉及新写路径，归编排器演进批次。
- 审计 Better fix：分支 criticality 声明机制。
