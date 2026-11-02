# Feature: `frontend_production_shell`

> **后续状态（2026-10-11）**：本 feature 建立的页面路由与壳层结构仍然成立，但其
> 「继续以 `.pen` 为视觉真源」的约定已被前端 UI 整套迁移
> （[`frontend_design_port`](../frontend_design_port/feature.md)）取代：当前视觉真源是
> `english-oral-practice-app` 原型，`designs/echowhale-mvp.pen` 不再作为实现依据。
> 壳层本身也从共享应用导航改为 `AppShell`（navbar/footer）承载全部 11 条路由。

## 基本信息

- `feature`: `frontend_production_shell`
- `status`: `in_progress`
- `branch`: `feature/frontend_app/frontend-production-shell`
- `module`: `frontend_app`
- `cross_module`: `no`
- `owner`: `codex`
- `updated_at`: `2026-04-01`

## 背景

`designs/echowhale-mvp.pen` 已经提供首页上传、启动加载、练习会话、练后反馈、登录、注册六个核心 screen，但前端此前仍是“六屏切换预览器”，缺少真实路由、历史页、表单态、上传态、mock 契约和生产化壳层结构。

这一轮把目标从“可演示原型”升级为“可上线前端壳层”：继续以 `.pen` 为视觉真源，但前端要具备真实页面路由、稳定服务接口和后续替换后端 API 的落点。当前媒体上传已开始从 mock 过渡到真实后端接口。

## 用户故事

- 当我进入 EchoWhale 前端时
- 我希望看到的是一个真实产品应用，而不是原型切屏器
- 这样我就能继续接后端接口、补页面状态，并把这套界面作为上线前端继续演进

## 范围

### In scope

- 把 `frontend/src/App.tsx` 从预览切屏器重构为真实路由入口
- 新增首页、加载页、会话页、练后反馈页、历史页、登录页、注册页的真实页面模块
- 新增 mock service、契约类型和基础表单/上传/会话状态
- 建立 token/base/components/utilities 四层样式结构
- 为缺失的 `HistoryReview` 页面补齐代码实现和文档映射

### Out of scope

- 真实 session/history/auth FastAPI 业务路由接入
- 真实语音识别、真实账号体系
- 自动化 Pencil 双向同步

## 设计要点

- 主视觉继续对齐 `.pen` 的中文定稿，桌面端高保真、移动端保真改排
- 历史页采用“列表 + 详情侧板”结构，以复盘场景为核心
- 所有页面使用统一 token，不再把临时色值和布局散落到单体样式中
- 前端 service 接口要稳定到足以直接替换为真实 API provider

## 验收标准

- `[x]` 前端入口不再展示六屏切换导航
- `[x]` 路由已覆盖 `/`、`/session/loading`、`/session/:sessionId`、`/session/:sessionId/review`、`/history`、`/login`、`/register`
- `[x]` 历史页已实现“列表 + 详情侧板”结构
- `[x]` `mockApi` 已提供会话、反馈、历史、登录注册的契约占位
- `[x]` 关键路由流和 mock service 已有 Vitest 保护
- `[x]` `.pen` 中补齐 `Screen/HistoryReview`
- `[x]` 首页本地图片可在 loading 页触发真实 `POST /api/v1/media/upload`，失败时可停留在 loading 页重试

## 测试记录

- 主要测试命令：`npm test -- src/services/mediaApi.test.ts src/App.test.tsx src/services/mockApi.test.ts`
- 当前通过证据：
  - 生产路由首页默认显示首页上传且不再展示原型切屏导航
  - 首页可进入加载页，再进入会话页
  - 首页真实选图后，loading 页会调用 `media/upload`，成功后再进入会话页
  - 上传失败时会停留在 loading 页并显示重试入口
  - `/history` 可渲染历史列表和复盘详情结构
  - `/login` 可跳转到 `/register`
  - `mockApi` 可追加消息并校验登录错误态
- 已知缺口：
  - 除媒体上传外，当前仍是 mock service 驱动，尚未替换为真实 FastAPI 路由
