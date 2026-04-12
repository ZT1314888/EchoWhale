# Version: `<version_name>`

## 基本信息

- `version`: `<version_name>`
- `status`: `idle` | `integrating` | `full_flow_test_passed` | `releasable`
- `branch`: `integration/system` | `main`
- `created_at`: `<YYYY-MM-DD>`
- `published_at`: `<YYYY-MM-DD or blank>`

## 版本摘要

用一段话说明这个版本解决了什么问题，面向什么用户状态。

## 包含内容

- `api/`：
- `frontend/`：
- `tests/`：
- `docs/`：

## 完成情况

- 已完成：
- 未完成但可接受：
- 已知限制：

## 验证结果

- smoke：
- module：
- integration：
- full_flow：

## 控制面同步

- 若本版状态会影响系统总态，先更新 `docs/control/agent-control-plane.json`
- 同步后运行：`uv run python -m tools.agent_ops render`
- 校验：`uv run python -m tools.agent_ops check`

## 发布说明

- 发布前检查：
- 发布方式：
- 回滚方式：

## 后续工作

- 下一版要补什么：
- 哪些 feature 仍在 `planned` 或 `in_progress`：
