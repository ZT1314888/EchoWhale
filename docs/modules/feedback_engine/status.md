# Module Status: `feedback_engine`

## 基本信息

- `module`: `feedback_engine`
- `status`: `building`
- `branch`: `module/feedback_engine`
- `owner`: `unassigned`
- `updated_at`: `2026-03-30`

## 模块目标

输出短而可执行的学习反馈，至少覆盖 `Grammar`、`More Natural`、`Useful Words` 三类信息。

## 当前真相

- 现有实现：`api/modules/feedback_engine/` 目录已存在
- 已完成边界：schema、state、agent、service、prompts 与 correction tool 骨架
- 仍然缺失：反馈结构稳定性验证、异常输入兜底、最小回归测试

## 输入输出契约

- 输入：学习者回复、场景上下文、教练回复
- 输出：结构化反馈项
- 关键字段：`Grammar`、`More Natural`、`Useful Words`

## 代码位置

- `api/modules/feedback_engine/`

## 当前工作

- `[ ]` 固定反馈输出结构
- `[ ]` 补短反馈约束说明
- `[ ]` 补核心 schema 与 service 测试

## 测试门

- `module_test_passed` 的标准：三类反馈字段稳定存在且内容简短可读
- 最少要覆盖的用例：正常反馈、输入过短、输入异常
- 还没覆盖的风险：真实模型生成长度和字段一致性

## 阻塞项

- 真实生成链路尚未接入

## 变更记录

- `2026-03-30`：初始化模块状态文档
