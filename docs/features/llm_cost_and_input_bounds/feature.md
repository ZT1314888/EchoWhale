# LLM 成本与输入边界（llm_cost_and_input_bounds）

> 审计报告（audit-report-EchoWhale-2026-10-01.md）Finding 10 / Finding 11 修复。
> Trellis 任务：`.trellis/tasks/10-02-llm-cost-and-input-bounds`。

## 目标

LLM 请求无 `max_tokens`（单次成本上不封顶）、usage 仅打日志（成本不可归因）、learner_message/语音 transcript 无长度上限（2MB 输入直进 prompt 并撑大 Text 列）、教练输出无硬顶。

## 实现说明

### 1. 输出预算（F10a）

`OpenAICompatibleClient` 构造期注入 `max_tokens`（None 时不发送字段，向后兼容），两个 payload builder（文本/图像）统一写入；三引擎从 settings 接线：coach 300 / feedback 400 / scene 500。

### 2. 用量账本（F10b）

- 迁移 0012：`llm_usage(model, prompt_tokens, completion_tokens, total_tokens, created_at)`，created_at 建索引支持按天聚合。
- `usage_recorder` 参数升级为 `usage_sink` Protocol（同步签名）；记录顺序固定"先 logger 后 sink"，整包与流式共用 `_record_usage` 单一路径；sink 异常降级 `llm_usage_sink_failed` warning，绝不影响补全主流程（旁路观测非业务依赖）。
- 默认 sink 为 sync 域仓储（auth 同款）：事件循环内 fire-and-forget 线程池写入（强引用防 GC），纯同步路径当前线程写；`build_llm_usage_sink()` 惰性解析 session_factory，无 DATABASE_URL 的构造期（单测）也安全。
- owner/session 归因不做（待 request-id/上下文贯穿批次）；当前账本已支持"按 model × 按天"的成本回答。

### 3. 输入边界（F11）

- `learner_message` ≤2000 字符、`VoiceConversationTurn.content` ≤4000、`conversation` ≤200 turns——engine schema 与 `VoiceCompleteRequest` 契约层同步（路由按契约 DTO 校验）。
- 超限走既有 RequestValidationError → 400/1001 统一信封（注：本仓校验错误是 400 不是 422，与全局契约一致，未改处理器）。
- 教练输出硬顶：`_build_reply_turn` 超 `llm_coach_output_max_chars=2000` 截断 + `coach_reply_truncated` warning（流式与非流式共用该函数，天然全覆盖）。

## 验证

- +41 个测试（累计 429 passed / 2 skipped）：payload max_tokens 断言（三引擎 + None 兼容）、usage sink 两路径 + 失败隔离、边界 422/400、截断 warning、迁移 0012 可逆。
- ruff / black 全绿。

## 遗留

- owner/session 归因：等 request-id 中间件（本批次任务 D）之后用上下文贯穿补齐。
- fire-and-forget 写入在进程退出瞬间可能丢最后几条用量记录（旁路数据，可接受）；如需强一致改为有界队列 + 优雅排空。
- token 级限流（用量账本之上的升级）另行立项。
