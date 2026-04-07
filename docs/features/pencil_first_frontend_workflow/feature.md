# Feature: `pencil_first_frontend_workflow`

## 基本信息

- `feature`: `pencil_first_frontend_workflow`
- `status`: `in_progress`
- `branch`: `feature/frontend_app/pencil-first-workflow`
- `module`: `frontend_app`
- `cross_module`: `yes`
- `owner`: `codex`
- `updated_at`: `2026-04-01`

## 背景

EchoWhale 目前已经有后端模块骨架，但前端仍停留在空目录状态，设计资产也没有固定真源。继续直接写前端页面会导致页面结构、组件命名和视觉约定不断漂移，后续既难以复用，也难以把页面回写成可持续维护的原型。

当前这条 feature 已进一步收敛：设计真源不再是英文草稿或中文 demo，而是 `designs/echowhale-mvp.pen` 的中文六屏定稿；前端目标也从“先做 demo 演示态”切换为“按定稿逐屏复刻”。

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
- `[x]` `.pen` 已完成新的上传、启动、会话、练后反馈、登录、注册六屏原型流
- `[x]` `.pen` 六个核心 screen 已完成中文化并成为当前真源
- `[x]` React 页面已按中文 `.pen` 六屏逐屏回贴，旧 demo 壳层已移除

## 测试记录

- `feature_test_passed` 的证据：已满足基础前端验证门槛；`frontend/` 下 `npm test` 与 `npm run build` 已通过，Pencil 六屏也已完成截图检查与布局体检
- 主要测试命令：`npm test`、`npm run build`、Pencil `snapshot_layout`
- 已完成验证：
  - `designs/echowhale-mvp.pen` 已重构为 `Screen/HomeUpload`、`Screen/PracticeLaunch`、`Screen/PracticeSession`、`Screen/PostPracticeReview`、`Screen/Login`、`Screen/Register`
  - 对首页、启动页、会话页、练后反馈页、登录页、注册页执行了 Pencil 截图检查
  - 对设计文件执行了 `snapshot_layout(..., problemsOnly=true)`，结果为 `No layout problems.`
- 本轮新增事实：
  - `designs/echowhale-mvp.pen` 已把六个核心 screen 的标题、按钮、字段和说明文案切成简体中文
  - `frontend/src/App.tsx` 与 `frontend/src/styles.css` 已移除旧 demo 信息架构，改为按中文定稿六屏复刻
  - `frontend/` 已完成 `npm test` 与 `npm run build`，当前六屏复刻原型具备可运行、可验证的前端交付形态
- 已知缺口：
  - 当前后端 API 路由未补齐，前端只能验证契约占位和结构映射
  - 逐屏“前端页面 vs `.pen` 截图”的人工对照说明仍需在后续评审中继续细化

## 合并与关闭

- 何时可以写成 `merged_to_module`
  当前 feature 的文档、设计资产和前端壳层都完成并通过 feature 级验证后
- 何时可以写成 `closed`
  当前工作流在至少一个真实页面上完成一次设计、实现和回写闭环后
- 相关文档链接：
  - `docs/control/pencil-workflow.md`
  - `docs/modules/frontend_app/design_mapping.md`
  - `docs/versions/2026-03-31-pencil-first-progress.md`
