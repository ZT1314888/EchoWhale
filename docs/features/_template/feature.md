# Feature: `<feature_name>`

## 基本信息

- `feature`: `<feature_name>`
- `status`: `planned` | `in_progress` | `feature_test_passed` | `merged_to_module` | `closed`
- `branch`: `feature/<module-name>/<feature-name>`
- `module`: `<primary_module_name>`
- `cross_module`: `yes` | `no`
- `owner`: `<owner>`
- `updated_at`: `<YYYY-MM-DD>`

## 背景

这件事为什么要做。只写用户价值和当前痛点，不写实现细节。

## 用户故事

- 当我...
- 我希望...
- 这样我就...

## 范围

### In scope

- ...
- ...

### Out of scope

- ...
- ...

## 设计要点

- 关键流程：
- 依赖模块：
- 如果 `cross_module = yes`，这里必须写清主责任模块和联动模块：
- 关键数据：
- 失败时如何处理：

## 验收标准

- `[ ]` ...
- `[ ]` ...
- `[ ]` ...

## 测试记录

- `feature_test_passed` 的证据：
- 主要测试命令：
- 已知缺口：

## 合并与关闭

- 何时可以写成 `merged_to_module`
- 何时可以写成 `closed`
- 相关文档链接：
