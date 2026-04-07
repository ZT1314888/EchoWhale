# Module Status: `frontend_app`

## 基本信息

- `module`: `frontend_app`
- `status`: `building`
- `branch`: `module/frontend_app`
- `owner`: `codex`
- `updated_at`: `2026-04-07`

## 模块目标

提供图片上传、会话练习、反馈展示和历史查看的前端壳层与交互体验。

## 当前真相

- 现有实现：`frontend/` 已从六屏预览壳层重构为真实路由应用，包含首页上传、启动加载、会话、练后反馈、历史、登录、注册七个页面入口
- 已完成边界：设计工作流文档、Pencil 设计源、设计映射文档、mock service 契约、路由级页面结构、基础上传/表单/消息交互、历史复盘侧板
- 已完成边界：首页 `index` 已改为独立品牌顶栏 + 上传主卡 + 三列示例场景区，并回到与 `.pen` 设计稿一致的轻量首屏结构
- 已完成边界：`StartupLoading` 已升级为独立动态分析页，包含中心品牌 logo、扩散圆环、阶段型进度 pill 和完成后才激活的练习入口
- 已完成边界：首页本地图片选择后，会在 `StartupLoading` 页发起真实 `POST /api/v1/media/upload`，上传成功后再调用真实 `POST /api/v1/sessions` 进入练习页
- 已完成边界：首页示例场景不再创建 mock `session-*`；现在会调用真实 `POST /api/v1/sessions` with `sample_scene_id`，进入真实 `sess_*` 练习页并可继续使用语音、review 与 history
- 已完成边界：首页上传链路已适配统一响应壳，媒体上传成功从 `data` 解包、失败从 `message` 读取错误信息
- 已完成边界：`PostPracticeReview` 与 `History` 已切到真实 review/history API，不再依赖 mock 数据
- 已完成边界：练后反馈页失败态已在前端收口，不再透传后端英文 `Session review ... not found`
- 已完成边界：登录/注册、refresh 恢复和 `History` 路由守卫已切到真实 auth API，匿名主路径会自动携带 `visitor_id`
- 已完成边界：注册成功后改为回到登录页，登录后右上角收口为昵称悬浮菜单并提供退出登录
- 已完成边界：登录成功后首页会展示一次性成功提示，支持自动消失与手动关闭
- 已完成边界：`PracticeSession` 页桌面端已收口为“左侧 logo 主舞台 + 右侧实时对话”的双栏语音练习区，移动端仍保持单栏且主对话优先
- 已完成边界：`PracticeSession` 现已移除文本输入框、顶栏与旧侧栏，左栏只保留可点击鲸鱼 logo；logo 本身兼任 start/end 单按钮，并在点击后切换到持续 wifi 动效
- 已完成边界：`PracticeSession` 对话流会在新消息到来时自动定位到最新消息位置，并隐藏显眼滚动条视觉，避免出现右侧拖拽条观感
- 已完成边界：前端已从浏览器 `Web Speech API` 切到 Deepgram Voice Agent bootstrap + WebSocket 实时语音链路，练习页会实时显示 `ConversationText`，并在结束会话时调用后端 `voice/complete` 写回 transcript 与 review
- 仍然缺失：更完整的系统联调细节，以及真实私有 R2 可访问性确认
- 当前策略补充：前端展示层继续以中文 `.pen` 为唯一真源，但代码入口已不再保留 demo 切屏器，而是面向生产应用骨架

## 输入输出契约

- 输入：图片文件、会话数据、反馈数据、历史数据
- 输出：页面状态、交互反馈、可视化展示
- 关键字段：上传状态、消息列表、反馈卡片、历史列表

## 代码位置

- `frontend/`

## 当前工作

- `[x]` 初始化可运行前端工程
- `[x]` 对齐后端 API 契约的设计语义和 mock 数据结构
- `[x]` 定义上传页、练习页、历史页最小壳层
- `[x]` 按新的 Pencil 设计稿完成原型重设计
- `[x]` 补充可复用品牌 `Logo` 组件封装
- `[x]` 按中文化后的 Pencil 六屏定稿完成前端代码复刻
- `[x]` 移除旧的营销型 demo 壳层，替换为真实路由应用入口
- `[x]` 新增 `mockApi`、前端契约类型和关键路由测试
- `[x]` 实现 `History` 列表 + 详情侧板页面
- `[x]` 将 `HistoryReview` 正式回写到 `.pen`
- `[x]` 形成本轮全量前端构建、测试与逐屏对照验证证据
- `[x]` 将首页从共享应用壳层收口为设计稿 `index` 的独立首屏布局
- `[x]` 将启动分析页从静态加载卡重构为独立动态分析舞台
- `[x]` 接入真实 `media/upload` API，形成“选图 -> loading 上传 -> 进入练习”的前端主路径
- `[x]` 将首页示例场景切到真实 session start API，示例练习流不再依赖 mock session id
- `[x]` 将练习页切到真实 session `start/get/reply` API，上传后的练习流不再依赖 mock session
- `[x]` 将练后反馈页切到真实 review API
- `[x]` 将历史页切到真实 history 列表与详情 API
- `[x]` 将登录/注册页切到真实 auth API，并为 `/history` 增加登录守卫
- `[x]` 将注册流程收口为“先建号再登录”，并让首页/应用头部接入真实登录态菜单
- `[x]` 将练习页从本地浏览器语音识别切到 Deepgram Voice Agent bootstrap / complete API
- `[x]` 将语音练习页重构为左侧 logo 主舞台 + 右侧实时对话双栏布局，并补自动滚动到最新消息
- `[x]` 新增 `useDeepgramVoiceAgent` hook，接入 WebSocket、PCM 采集、音频播放与 transcript 状态管理

## 测试门

- `module_test_passed` 的标准：至少有最小可运行前端壳层并能对齐后端契约，关键上传主路径可调用真实接口，且前端构建与测试有明确通过证据
- 最少要覆盖的用例：上传入口、会话展示、历史入口
- 还没覆盖的风险：真实 R2 外链可访问性尚未完成联调；匿名 visitor 与登录用户的端到端系统联调还需补一次；真实浏览器麦克风权限、Deepgram token 与生产网络环境仍需补 smoke

## 阻塞项

- 真实私有 R2 结果与带认证态的全链路联调尚未收口

## 变更记录

- `2026-03-30`：初始化模块状态文档
- `2026-03-31`：补齐 Pencil-first 工作流文档，生成 MVP `.pen` 原型文件，并初始化前端工程骨架
- `2026-03-31`：将 `.pen` 重构为 `HomeUpload / PracticeLaunch / PracticeSession / PostPracticeReview / Login / Register` 六屏流
- `2026-03-31`：新增 `frontend/src/components/Logo.jsx`，封装鲸鱼品牌 SVG 供页面回贴复用
- `2026-03-31`：修复 `SessionStage.tsx` 中未转义箭头文本导致的前端构建错误
- `2026-03-31`：将 `App.tsx` 页头中的 `EW` 占位替换为真实 `Logo` 组件
- `2026-03-31`：将 `designs/echowhale-mvp.pen` 六个核心 screen 全量中文化，中文定稿成为当前前端复刻基准
- `2026-03-31`：重写 `frontend/src/App.tsx` 与 `frontend/src/styles.css`，移除旧 demo 壳层并按中文 `.pen` 六屏结构完成 1:1 复刻
- `2026-04-01`：补录验证证据，确认 `frontend/` 下 `npm test` 与 `npm run build` 已通过，并将今日进度归档到版本文档
- `2026-04-01`：将前端入口重构为真实路由应用，新增 `HomeUpload / StartupLoading / PracticeSession / PostPracticeReview / History / Login / Register` 页面模块
- `2026-04-01`：新增 `frontend/src/services/mockApi.ts` 与 `frontend/src/types/app.ts`，补齐会话、反馈、历史和认证的前端契约层
- `2026-04-01`：在 `designs/echowhale-mvp.pen` 中新增 `Screen/HistoryReview`，并完成截图级人工核对
- `2026-04-01`：将首页 `HomeUpload` 从共享导航壳层改为独立 `index` 顶栏，补齐上传卡与示例场景区样式，并确认 `npm test`、`npm run build` 通过
- `2026-04-01`：将 `StartupLoading` 重构为独立分析页，增加品牌 logo 中心动画、扩散圆环、阶段进度状态和 CTA 延迟激活逻辑
- `2026-04-01`：新增 `frontend/src/services/mediaApi.ts`，并将本地图片上传接到真实后端 `POST /api/v1/media/upload`，补齐成功/失败路径测试与构建验证
- `2026-04-02`：同步适配后端统一响应壳，上传成功从 `data` 解包、错误从 `message` 展示，媒体上传主路径保持可用
- `2026-04-03`：新增 `practiceApi` / `sessionApi`，上传后调用真实 session start，练习页读取与回复切到真实 session get/reply
- `2026-04-04`：新增 `reviewApi` / `historyApi`，练后反馈页与历史页切到真实后端读取，sample review 仍保留 mock fallback
- `2026-04-05`：新增真实 auth API、前端登录态恢复与 `/history` 守卫，匿名主路径改为自动携带 `visitor_id`
- `2026-04-05`：注册成功后改为跳转登录页，首页与应用头部接入昵称菜单和退出登录
- `2026-04-05`：修复昵称悬浮菜单因 hover 空隙与即时关闭导致的回缩问题，退出登录项恢复可点击
- `2026-04-05`：登录成功后新增首页 success toast，使用一次性路由状态触发，并在首页消费后立即清空避免重复弹出
- `2026-04-05`：调整 `PracticeSession` 页桌面端双栏顺序为左提示右主区，移动端继续保持主练习内容优先
- `2026-04-05`：移除注册页昵称、邮箱和密码的示例预填值，保留注册成功后登录页邮箱自动带入
- `2026-04-05`：为登录页和注册页补充前端空值校验，邮箱/密码为空时改为中文“不能为空”提示，并阻止继续发起 auth 请求
- `2026-04-05`：为登录失败补充前端错误映射，邮箱或密码错误时统一显示 `邮箱/密码错误`，不再透传英文 `Invalid email or password`
- `2026-04-05`：收口练后反馈页失败态，review 缺失时不再展示后端英文 `Session review ... not found`，页面仅保留中文标题与返回练习入口
- `2026-04-06`：loading 页新增 session 创建失败处理；unsupported scene image 会停留当前页并提示用户返回首页换图
- `2026-04-06`：将 `PracticeSession` 从双栏文本补充页重构为沉浸式单栏语音页，移除文本输入框并新增浏览器语音转写、`Talk To Your Agent / End Conversation` 入口与结束后 review 跳转
- `2026-04-06`：将 `PracticeSession` 从浏览器 `Web Speech API` 切到 Deepgram Voice Agent，新增 `voice/bootstrap` / `voice/complete` API 消费与 `useDeepgramVoiceAgent` 实时会话 hook
- `2026-04-07`：新增 `createSamplePracticeSession`，并将首页示例场景从 mock `session-*` 切到真实 `sess_*` 会话创建；sample 练习页现在可继续走真实 voice/review/history
- `2026-04-07`：将 `PracticeSession` 从沉浸式单栏语音页调整为桌面端双栏布局，左侧收口为单一鲸鱼 logo 按钮与 wifi 动效主舞台，右侧独立实时对话，并在新消息到来时自动滚动到最新位置




