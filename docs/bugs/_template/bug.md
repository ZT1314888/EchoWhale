# Bug: `<bug_title>`

## 基本信息

- `bug`: `<bug_title>`
- `status`: `planned` | `in_progress` | `feature_test_passed` | `merged_to_module` | `closed`
- `branch`: `bugfix/<module-name>/<bug-name>`
- `owner`: `<owner>`
- `reported_at`: `<YYYY-MM-DD>`
- `affected_area`: `<module or feature>`
- `merge_target`: `module/<module-name>`

## 现象

用一句话说明用户看到了什么异常。

## 复现步骤

1. ...
2. ...
3. ...

## 预期结果

- ...

## 实际结果

- ...

## 影响范围

- 用户影响：
- 模块影响：
- 数据影响：

## 根因

写清楚真正的技术原因，避免只描述表面现象。

## 修复方案

- 改了什么：
- 为什么这样改：
- 是否有兼容性风险：

## 验证

- 测试命令：
- 验证结果：
- 仍需关注：

## 控制面同步

- 若该 bug 会影响控制台摘要、模块状态或测试层状态，先更新 `docs/control/agent-control-plane.json`
- 同步后运行：`uv run python -m tools.agent_ops render`
- 校验：`uv run python -m tools.agent_ops check`

## 关闭条件

- 什么条件下可以从 `in_progress` 变成 `feature_test_passed`
- 什么条件下可以从 `feature_test_passed` 变成 `merged_to_module`
- 什么条件下可以从 `merged_to_module` 变成 `closed`
