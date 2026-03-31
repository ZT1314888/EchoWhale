# Feature: `pencil_first_frontend_workflow`

## 基本信息

- `feature`: `pencil_first_frontend_workflow`
- `status`: `in_progress`
- `branch`: `feature/frontend_app/pencil-first-workflow`
- `module`: `frontend_app`
- `cross_module`: `yes`
- `owner`: `codex`
- `updated_at`: `2026-03-31`

## 背景

EchoWhale 目前已经有后端模块骨架，但前端仍停留在空目录状态，设计资产也没有固定真源。继续直接写前端页面会导致页面结构、组件命名和视觉约定不断漂移，后续既难以复用，也难以把页面回写成可持续维护的原型。

## 用户故事

- 当我规划 EchoWhale 的产品页面时
- 我希望原型、页面结构和前端组件有一套稳定的共用语言
- 这样我就能用 Pencil 持续设计、落代码、再回写，而不是每次重画

## 范围

### In scope

- 将 Pencil 明确为 EchoWhale 的主设计源
- 新增 `.pen` 设计资产目录与说明
- 为 `frontend_app` 建立设计映射文档
- 初始化 `React + Tailwind` 前端壳层
- 实现首个映射页面和共享组件

### Out of scope

- 完整自动化双向同步
- 所有前端页面一次性补齐
- 真实后端 API 全量接入
- Figma 并行工作流

## 设计要点

- 关键流程：Pencil 原型 -> 映射文档 -> React + Tailwind 页面 -> 关键页面回写
- 依赖模块：`frontend_app`、`platform_foundation`、`session_orchestration`
- 如果 `cross_module = yes`，这里必须写清主责任模块和联动模块：
  主责任模块是 `frontend_app`；联动模块是 `platform_foundation` 和 `session_orchestration`，因为前端契约需要对齐现有 session schema 和未来 API 接入边界。
- 关键数据：scene、role、opener、messages、feedback、history summary
- 失败时如何处理：在前端使用 mock 状态兜底并显式展示“API 尚未接入”，不伪造真实接口行为

## 验收标准

- `[x]` `designs/` 中存在 EchoWhale 的主 `.pen` 文件和说明文档
- `[x]` `docs/control/` 中存在 Pencil 工作流规范
- `[x]` `docs/modules/frontend_app/` 中存在设计到代码映射文档
- `[x]` `frontend/` 已初始化 React + Tailwind + Vitest 工程骨架
- `[ ]` 首个页面壳层已对齐上传、练习、反馈、历史四类核心信息

## 测试记录

- `feature_test_passed` 的证据：尚未满足；当前只完成了 Pencil 页面截图检查与布局体检
- 主要测试命令：`npm test`、`npm run build`、Pencil `snapshot_layout`
- 已完成验证：
  - `designs/echowhale-mvp.pen` 已生成并包含 `Screen/Home`、`Screen/PracticeSession`、`Screen/HistoryReview` 和组件库
  - 对三个页面执行了 Pencil 截图检查
  - 对三个页面执行了 `snapshot_layout(..., problemsOnly=true)`，结果均为 `No layout problems.`
- 已知缺口：
  - 当前后端 API 路由未补齐，前端只能验证契约占位和结构映射
  - 前端测试和构建尚未形成可引用的最终通过证据

## 合并与关闭

- 何时可以写成 `merged_to_module`
  当前 feature 的文档、设计资产和前端壳层都完成并通过 feature 级验证后
- 何时可以写成 `closed`
  当前工作流在至少一个真实页面上完成一次设计、实现和回写闭环后
- 相关文档链接：
  - `docs/control/pencil-workflow.md`
  - `docs/modules/frontend_app/design_mapping.md`
  - `docs/versions/2026-03-31-pencil-first-progress.md`
