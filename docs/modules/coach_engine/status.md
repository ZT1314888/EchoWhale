# Module Status: `coach_engine`

## 基本信息

- `module`: `coach_engine`
- `status`: `building`
- `branch`: `module/coach_engine`
- `owner`: `unassigned`
- `updated_at`: `2026-03-30`

## 模块目标

在给定场景和对话上下文下生成角色一致、可继续追问的英语陪练回复。

## 当前真相

- 现有实现：`api/modules/coach_engine/` 目录已存在
- 已完成边界：schema、state、agent、service、chat provider 骨架
- 仍然缺失：回复策略验证、多轮上下文覆盖、异常路径测试

## 输入输出契约

- 输入：场景设定、历史消息、学习者回复
- 输出：教练式回应、下一步交流推进
- 关键字段：`role`、上下文消息、回复文本

## 代码位置

- `api/modules/coach_engine/`
- 相关 provider：`api/modules/coach_engine/providers/`

## 当前工作

- `[ ]` 明确多轮上下文最小契约
- `[ ]` 补教练式回复和追问验证
- `[ ]` 明确角色一致性检查点

## 测试门

- `module_test_passed` 的标准：多轮上下文下回复结构稳定、角色不漂移
- 最少要覆盖的用例：首轮回复、连续追问、空历史兜底
- 还没覆盖的风险：真实 LLM 接入后的稳定性差异

## 阻塞项

- 真实聊天 provider 尚未接入

## 变更记录

- `2026-03-30`：初始化模块状态文档
