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
| `Screen/HomeUpload` | 首页上传页 | `implemented` | 首页已改为独立 `index` 顶栏，保留居中品牌字标、右上认证入口、上传主卡和三列示例场景区 |
| `Screen/StartupLoading` | 启动加载页 | `implemented` | 已收口为独立动态分析舞台：中心品牌 logo、向外扩散圆环、三阶段进度和完成后激活的 CTA |
| `Screen/PracticeSession` | 练习会话页 | `implemented` | 复刻场景头、双消息卡、语音底座和即时提示 |
| `Screen/PostPracticeReview` | 练后反馈页 | `implemented` | 复刻回响 hero 与四张反馈卡，不再额外重组信息架构 |
| `Screen/Login` | 登录页 | `implemented` | 左侧 `AuthAside` + 右侧 `AuthPanel` 双栏结构 |
| `Screen/Register` | 注册页 | `implemented` | 左侧 `AuthAside` + 右侧注册表单卡，沿用中文定稿 |
| `Screen/HistoryReview` | 历史页 | `implemented` | 已按列表 + 详情侧板结构回写到 `.pen` 并落地到前端代码 |

## Component Mapping

| Pencil component | Frontend target | 状态 | 说明 |
| --- | --- | --- | --- |
| `Component/UploadSceneCard` | 首页上传主卡 | `designed` | 上传、样例入口、场景提示 |
| `Component/FeatureStrip` | 首页特性条 | `designed` | 场景识别、角色对话、练后回响 |
| `Component/SceneMiniHeader` | 会话页和启动页顶部场景条 | `designed` | 极简场景、角色和开场提示 |
| `Component/WhaleLaunchCard` | 启动页鲸鱼主卡 | `designed` | 点击鲸鱼或主按钮直接进入对话 |
| `Component/DialogBubble` | 对话气泡 | `designed` | 区分 coach / learner 的消息块 |
| `Component/VoiceDock` | 语音输入底座 | `designed` | 语音主入口，文字为辅 |
| `Component/LiveHintCard` | 练中轻提示 | `designed` | 只提供一条即时建议，不做重反馈 |
| `Component/ReviewHero` | 练后反馈页顶部总结区 | `designed` | 用于承接本轮回响和下一步建议 |
| `Component/ReviewMetricCard` | 练后反馈指标卡 | `designed` | 展示具体反馈项 |
| `Component/AuthPanel` | 登录表单主卡 | `designed` | 认证表单容器 |
| `Component/AuthAside` | 登录 / 注册页侧边说明 | `designed` | 承接产品文案和品牌气质 |
| `Component/HistoryList` | 历史列表 | `code_implemented` | 承载历史练习列表与选中状态 |
| `Component/HistoryDetailPanel` | 历史详情侧板 | `code_implemented` | 承载消息回放、反馈摘要和再次练习入口 |

## 回写规则

- 只对 `Screen/*` 和 `Component/*` 级对象执行正式回写。
- 当前端页面结构变化影响多个组件时，先更新 `.pen` 再调整映射表。
- 当前端只发生小样式调整时，可以只更新代码，不强制改 `.pen`。

## 当前实现说明

- 当前设计真源已经切换为 `designs/echowhale-mvp.pen` 的中文七屏定稿，其中 `HistoryReview` 已完成 screen 级回写。
- 首页 `HomeUpload` 已从共享应用导航壳层收口为设计稿里的独立首屏结构，后续如只做小样式微调，可继续在代码侧收敛。
- `StartupLoading` 已从共享页头 + 静态加载卡收口为独立分析页，动效以设计稿品牌 logo 为中心，后续优先只做节奏和像素级微调。
- `frontend/src/App.tsx` 已改为真实路由入口，不再保留六屏切换壳层。
- 前端页面结构、文案和卡片顺序仍以中文 `.pen` 为主要参照，但由于后端 API 尚未暴露，当前会话、历史和认证均由 `mockApi` 契约层承载。
- 样式层已拆为 `tokens / base / components / utilities` 四层，作为后续继续贴合 `.pen` 和替换真实 API 的稳定基础。
