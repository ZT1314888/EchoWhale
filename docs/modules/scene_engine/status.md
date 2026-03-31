# Module Status: `scene_engine`

## 基本信息

- `module`: `scene_engine`
- `status`: `building`
- `branch`: `module/scene_engine`
- `owner`: `unassigned`
- `updated_at`: `2026-03-30`

## 模块目标

根据图片或媒体信息输出场景类型、角色设定、开场白、关键标签和置信度。

## 当前真相

- 现有实现：`api/modules/scene_engine/` 目录已存在
- 已完成边界：schema、state、agent、service、mock vision provider 骨架
- 仍然缺失：更强的契约测试、异常路径验证、真实 provider 接入前的边界说明

## 输入输出契约

- 输入：图片分析输入或媒体上下文
- 输出：场景、角色、开场白、标签、置信度
- 关键字段：`scene`、`role`、`opener`、`labels`

## 代码位置

- `api/modules/scene_engine/`
- 相关 provider：`api/modules/scene_engine/providers/`

## 当前工作

- `[ ]` 收敛 provider 契约
- `[ ]` 明确异常和兜底输出
- `[ ]` 补核心 schema 与 agent 路径测试

## 测试门

- `module_test_passed` 的标准：合法输入时输出结构稳定，异常输入时有明确兜底
- 最少要覆盖的用例：正常分析、空输入、低置信度兜底
- 还没覆盖的风险：真实视觉模型接入后的返回结构波动

## 阻塞项

- 真实 provider 仍未接入

## 变更记录

- `2026-03-30`：初始化模块状态文档
