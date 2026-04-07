# Module Status: `feedback_engine`

## 基本信息

- `module`: `feedback_engine`
- `status`: `building`
- `branch`: `module/feedback_engine`
- `owner`: `unassigned`
- `updated_at`: `2026-04-05`

## 模块目标

输出短而可执行的学习反馈，至少覆盖 `Grammar`、`More Natural`、`Useful Words` 三类信息。

## 当前真相

- 现有实现：`api/modules/feedback_engine/` 已支持图片 `vocab_candidates` 输入，并保留 mock / live 双路径
- 已完成边界：schema、agent、service、prompts、基于教学词优先的 useful words 选择逻辑
- live 模式下已完成主文本模型联调，`feedback_engine` 已能返回真实结构化反馈

## 输入输出契约

- 输入：学习者回复、场景上下文、教学词汇候选
- 输出：结构化反馈项
- 关键字段：`Grammar`、`More Natural`、`Useful Words`

## 代码位置

- `api/modules/feedback_engine/`

## 当前工作

- `[x]` 固定反馈输出结构
- `[x]` 让 `Useful Words` 优先继承 `vocab_candidates`
- `[x]` 补 `vocab_candidates` 优先与 scene fallback 的回归测试
- `[x]` 用真实文本主模型验证结构化反馈可用
- `[ ]` 继续验证文本兜底模型的 JSON 输出稳定性

## 测试门

- `module_test_passed` 的标准：三类反馈字段稳定存在，且教学词优先进入 useful words
- 当前证据：`tests/modules/test_feedback_engine.py` 已覆盖 `vocab_candidates` 优先和 scene fallback
- 还没覆盖的风险：真实模型 JSON 格式波动、文本兜底模型在 JSON-only 任务下超时或断开

## 阻塞项

- 主文本模型已完成 live 联调，文本兜底模型仍需更换或继续调试

## 变更记录

- `2026-04-06`：将输入契约升级为 `vocab_candidates`，不再直接消费视觉标签
- `2026-03-30`：初始化模块状态文档


