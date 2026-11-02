# 2026-04-08 Agent Runtime P0 Progress

## Summary

本轮先落地 EchoWhale agent runtime 升级的第一批可收口能力，目标是把语音链路和 think proxy 从“能跑”推进到“有事实层、有约束、可回归”。

## Delivered

- 新增 `session_events` 与 `voice_session_facts` 两类运行事实模型与持久化表。
- `voice/bootstrap` 现在会记录 `voice_bootstrapped` event，并保存活跃语音会话事实。
- `voice/complete` 现在会落：
  - `voice_finalized` event
  - `review_built` event
  - `termination_reason`
  - `client_diagnostics`
  - transcript turn count
- Deepgram think proxy 现在不再接受任意 model 透传；若请求 model 与当前允许的 think model 不一致，会直接拒绝。
- 前端 `PracticeSessionPage` 对 `scrollIntoView` 增加运行时保护，避免测试环境因为 DOM API 缺失而在进入会话页时崩溃。
- `voice/complete` 可靠性收口：
  - service 层把内部 Pydantic 校验异常统一翻译为业务 `Validation error`，避免异常路径泄漏成 500
  - 路由层增加 transcript 非空 + 至少一条 `user` turn 的入口校验
  - session repository 新增 `finalize_voice_session` 原子收口写入，避免 transcript 与 review/events/facts 出现半完成状态
  - 清理 feedback engine 的重复 `_should_use_live_feedback()` 定义，降低维护噪音

## Verification Scope

- 后端新增回归测试覆盖：
  - voice bootstrap/finalize 运行事实
  - session repository 持久化运行事实
  - think proxy model mismatch 拒绝

## Verification Results

- `uv run pytest tests/modules/test_session_engine.py tests/db/test_session_repository.py tests/api/test_deepgram_routes.py tests/api/test_session_routes.py -q`
  - 结果：`40 passed in 3.44s`
- `uv run pytest -q`
  - 结果：`123 passed, 2 skipped in 16.78s`
- `npm test -- --run src/pages/PracticeSessionPage.test.tsx src/App.test.tsx`
  - 结果：`31 passed`
- `npm test -- --run`
  - 结果：`75 passed`
- `uv run pytest tests/modules/test_session_engine.py::test_complete_voice_session_persists_transcript_and_generates_review tests/modules/test_session_engine.py::test_complete_voice_session_does_not_persist_transcript_when_feedback_generation_fails tests/modules/test_session_engine.py::test_complete_voice_session_rejects_empty_conversation_with_validation_error tests/modules/test_session_engine.py::test_complete_voice_session_rejects_conversation_without_user_turn tests/db/test_session_repository.py::test_sqlalchemy_session_repository_finalizes_voice_session_atomically tests/api/test_session_routes.py::test_complete_voice_session_persists_transcript_and_returns_review tests/api/test_session_routes.py::test_complete_voice_session_rejects_empty_conversation_payload tests/api/test_session_routes.py::test_complete_voice_session_rejects_payload_without_user_turn -q`
  - 结果：`8 passed in 1.74s`

## Remaining Verification Gaps

- 新 migration 还未做真实数据库 upgrade / downgrade smoke。
- `history` 分页相关用例目前与仓库中未完成分页能力不一致，仍需独立收口，不属于本轮 voice 可靠性修复范围。

## Next

- 把 `scene_analyzed / coach_replied / feedback_generated` 也纳入统一 session event。
- 为 runtime facts 增加 route 级读取出口，供 history/review/debug 使用。
- 继续推进 memory extraction、retrieval hit 记录和 eval 扩展。
