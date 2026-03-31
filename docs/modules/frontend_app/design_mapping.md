# Frontend App Design Mapping

## 目标

记录 EchoWhale 的 Pencil 设计对象与前端实现对象之间的稳定映射，避免原型和代码各说各话。

## 当前设计源

- 主设计文件：`designs/echowhale-mvp.pen`
- 工作流规范：`docs/control/pencil-workflow.md`

## Token Mapping

| Pencil variable group | 前端落点 | 说明 |
| --- | --- | --- |
| `color/*` | `src/styles.css` CSS variables | 主色、表面色、文本色、强调色 |
| `spacing/*` | `src/styles.css` CSS variables | 页面边距、模块间距、卡片内边距 |
| `radius/*` | `src/styles.css` CSS variables | 卡片、按钮、输入区圆角 |
| `shadow/*` | `src/styles.css` CSS variables | 关键卡片投影和浮层深度 |
| `type/*` | `src/styles.css` CSS variables | 标题字号、正文层级、标签尺寸 |

## Screen Mapping

| Pencil screen | Frontend target | 状态 | 备注 |
| --- | --- | --- | --- |
| `Screen/Home` | `src/App.tsx` 中的首页与主工作区 | `in_progress` | 当前先用单页壳层承载 |
| `Screen/PracticeSession` | `src/components/SessionStage.tsx` | `in_progress` | 展示 opener、messages 和反馈 |
| `Screen/HistoryReview` | `src/components/HistoryRail.tsx` | `in_progress` | 展示历史会话摘要 |

## Component Mapping

| Pencil component | Frontend target | 状态 | 说明 |
| --- | --- | --- | --- |
| `Component/UploadDropzone` | `src/components/UploadDropzone.tsx` | `planned` | 上传区和图片描述摘要 |
| `Component/SceneSummaryCard` | `src/components/SceneSummaryCard.tsx` | `planned` | 当前场景、角色、标签与置信度 |
| `Component/SessionMessage` | `src/components/SessionMessage.tsx` | `planned` | 会话消息和 learner / coach 区分 |
| `Component/FeedbackCard` | `src/components/FeedbackCard.tsx` | `planned` | 语法、自然表达、词汇建议 |
| `Component/HistoryItem` | `src/components/HistoryItem.tsx` | `planned` | 历史会话摘要 |

## 回写规则

- 只对 `Screen/*` 和 `Component/*` 级对象执行正式回写。
- 当前端页面结构变化影响多个组件时，先更新 `.pen` 再调整映射表。
- 当前端只发生小样式调整时，可以只更新代码，不强制改 `.pen`。

## 当前实现说明

- 由于后端 API 还未真正暴露前端路由，本轮前端实现以 mock data 为主。
- 当前目标是先建立设计语义、组件边界和 Tailwind token 习惯。
