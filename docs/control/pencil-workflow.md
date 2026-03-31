# EchoWhale Pencil Workflow

## 目标

为 EchoWhale 建立一套 `Pencil -> React + Tailwind -> Pencil 回写` 的半双向工作流。

这套工作流的目标不是自动同步所有页面细节，而是把下面三类内容稳定对齐：

- 设计变量
- 共享组件
- 核心页面结构

## 设计源规则

- EchoWhale 的页面原型和组件草案统一以 `designs/` 下的 `.pen` 文件为真源。
- 不再把 Figma 作为主设计源。
- 页面结构、信息层级和主要状态先在 Pencil 中完成，再进入前端实现。
- 当前阶段只要求关键页面和共享组件可回写，不要求所有局部样式改动都自动反推。

## 目录约定

- `designs/echowhale-mvp.pen`：当前主设计文件
- `designs/README.md`：设计资产说明和命名规则
- `docs/features/pencil_first_frontend_workflow/feature.md`：工作流 feature 记录
- `docs/modules/frontend_app/design_mapping.md`：Pencil 与前端组件映射

## 页面范围

首批纳入这套工作流的页面：

- 首页
- 上传入口
- 练习会话页
- 反馈展示区
- 历史记录页

当前策略：

- 桌面优先
- 移动端保证基础可用
- 暂不维护独立 mobile 双稿

## 设计变量规则

Pencil 中的变量分组必须至少覆盖：

- `color/*`
- `spacing/*`
- `radius/*`
- `shadow/*`
- `type/*`

前端落地时将这些变量映射为：

- CSS variables
- Tailwind theme token

不要在页面组件内散落无法追踪的临时色值和临时间距。

## 命名规则

页面名、Pencil 组件名、前端组件名必须语义一致。

推荐命名：

- `Screen/Home`
- `Screen/PracticeSession`
- `Screen/HistoryReview`
- `Component/UploadDropzone`
- `Component/SessionMessage`
- `Component/FeedbackCard`
- `Component/HistoryItem`

前端代码使用 PascalCase，同步保留相同语义：

- `UploadDropzone`
- `SessionMessage`
- `FeedbackCard`
- `HistoryItem`

## 设计 -> 代码

实现顺序固定如下：

1. 在 Pencil 中完成页面结构和组件拆分
2. 截图确认布局与层级
3. 更新 `docs/modules/frontend_app/design_mapping.md`
4. 在 `frontend/` 中按映射实现 React 组件
5. 使用 Tailwind token 对齐设计变量

不允许跳过第 3 步直接实现，否则后续回写会失真。

## 代码 -> Pencil 回写

以下情况必须回写 Pencil：

- 页面结构发生明显变化
- 新增共享组件
- 组件状态层级变化影响多个页面
- Tailwind token 有新增或重命名

以下情况可以不单独回写：

- 极小的文案改动
- 单点像素级微调
- 明显属于临时调试的布局试验

回写后必须同步更新映射文档，记录：

- 变更对象
- 对应代码位置
- 回写原因
- 是否影响共享组件

## 验证门

一个页面要视为接入工作流成功，必须满足：

- 在 Pencil 中存在对应 screen
- 在映射文档中存在对应记录
- 在前端中存在对应 React 组件或页面壳层
- 至少完成一次截图级人工比对

## 当前限制

- 后端 API 路由仍未补齐，前端首批以 mock data 和契约占位为主
- 当前双向工作流是“半双向”，不是自动代码反编译
- 如果未来要纳入更多页面，再按模块拆分更多 `.pen` 文件
