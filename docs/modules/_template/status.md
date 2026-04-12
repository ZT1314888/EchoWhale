# Module Status: `<module_name>`

## 基本信息

- `module`: `<module_name>`
- `status`: `planned` | `building` | `module_test_passed` | `merged_to_integration` | `closed`
- `branch`: `module/<module-name>`
- `owner`: `<owner>`
- `updated_at`: `<YYYY-MM-DD>`

## 模块目标

用一段话说明这个模块要解决什么问题，以及它和上游、下游模块的关系。

## 当前真相

- 现有实现：
- 已完成边界：
- 仍然缺失：

## 输入输出契约

- 输入：
- 输出：
- 关键字段：

## 代码位置

- 主代码位置：
- 相关 service：
- 相关 route：
- 相关 model / db / integration：

## 当前工作

- `[ ]` ...
- `[ ]` ...
- `[ ]` ...

## 测试门

- `module_test_passed` 的标准：
- 最少要覆盖的用例：
- 还没覆盖的风险：

## 控制面同步

- `docs/control/agent-control-plane.json` 中的模块状态、说明和 owner files 应与这里保持一致
- 同步后运行：`uv run python -m tools.agent_ops render`
- 校验：`uv run python -m tools.agent_ops check`

## 阻塞项

- ...

## 变更记录

- `<YYYY-MM-DD>`：...
