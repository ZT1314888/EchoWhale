# Frontend App Design Mapping

> **设计真源已变更（2026-10-11）**：本表在本批 UI 迁移中重建。当前真源是
> `C:\Users\lucky\Downloads\english-oral-practice-app`（作者本机下载的 Next.js 原型，
> 未纳入本仓库版本控制）。**Pencil 时代已于 2026-10-11 整体退役**：`designs/` 目录
> （含 `echowhale-mvp.pen`）与 `docs/control/pencil-workflow.md` 已从仓库删除，
> Pencil 不再作为现行或候选工作流。下表中标注 `historical` 的条目保留原样，
> 用于回溯迁移前的映射关系。批次说明见
> [`docs/features/frontend_design_port/feature.md`](../../features/frontend_design_port/feature.md)。

## 目标

记录 EchoWhale 的设计对象与前端实现对象之间的稳定映射，避免原型和代码各说各话。

## 当前设计源

- 主设计源：`C:\Users\lucky\Downloads\english-oral-practice-app`（Next.js 原型，仓库外）
  - 令牌与 plain-CSS 工具类：`src/app/globals.css`（200 行）
  - 共享原语：`src/components/ui.tsx`
  - 页面：`src/app/{page,login,register,verify-email,forgot-password,reset-password,analyzing,practice,review,history,progress}/`
- 历史真源：`designs/echowhale-mvp.pen`（已于 2026-10-11 删除；如需考古走 git 历史）

## Token Mapping

前端不再使用 `src/styles.css` 这一层；令牌集中在 `frontend/src/styles/theme.css` 的
`@theme` 块，Tailwind v4 会把它们编译成 `bg-paper` / `text-ink` / `font-display` /
`animate-float` 这类工具类。

| 原型令牌 | 前端落点 | 说明 |
| --- | --- | --- |
| `--font-sans` / `--font-display` / `--font-serif` | `theme.css` `@theme` + `index.html` Google Fonts | Inter / Space Grotesk / Fraunces |
| `--color-paper` / `--color-cream` / `--color-ink` / `--color-iris` / `--color-lime` | `theme.css` `@theme` | 页面底色、卡片色、正文色、主强调色、高亮色 |
| `--animate-float` / `-float-slow` / `-marquee` / `-pulse-ring` | `theme.css` `@theme` + `utilities.css` 的 keyframes | v4 的 `--animate-*` 只拼动画简写，keyframes 必须同页存在 |
| 原型 plain-CSS 类（`.noise` / `.grid-pattern*` / `.glass` / `.card-lift` / `.text-gradient*` / `.wave-bar` / `.stagger` / `.no-scrollbar` / `.font-display` / `.font-serif-accent`） | `frontend/src/styles/utilities.css` | **故意不带 `@layer`**，以免被 Tailwind 同名工具类盖过 |
| html/body/滚动条/`:focus-visible`/range/reduced-motion | `frontend/src/styles/foundations.css` | 原型没有 reduced-motion 回退，EchoWhale 补了一条 |

`theme.css` 砍掉了 grep 证实零使用的 9 项：`--color-peach`、`--color-mint`、
`--color-ink-soft`、`--color-iris-deep`、`--animate-spin-slow`、`--animate-gradient`、
`.ring-conic`、`.dot-pattern`、`--animate-fade-up`（连带只被它引用的 `gradientShift`
keyframe）。

## Screen Mapping

| 原型 screen | Frontend target | 状态 | 备注 |
| --- | --- | --- | --- |
| `app/page.tsx` | `src/pages/HomeUploadPage.tsx` | `implemented` | 营销 hero 与创作器合一；「话题 / 上传」双 tab，**砍掉**原型的「粘贴」tab（后端无文本入口） |
| `app/analyzing/` | `src/pages/StartupLoadingPage.tsx` | `implemented` | 三圈 iris 脉冲 + 白底鲸鱼标，阶段卡片与百分比承担真实进度 |
| `app/practice/` | `src/pages/PracticeSessionPage.tsx` | `implemented` | 左主舞台 + 右对话栏；保留 Deepgram 实时语音，叠加 TTS 跟读 / 快捷回复 / 金句锦囊 / 计时器 |
| `app/review/` | `src/pages/PostPracticeReviewPage.tsx` | `implemented` | 深色分数带 + 维度列 + 「导演笔记 / 逐字稿」双 tab；逐字稿走真实 `getHistorySessionMessages` + 游标 |
| `app/history/` | `src/pages/HistoryPage.tsx` | `implemented` | 统计带 + 搜索/筛选/排序工具栏 + 列表详情双栏 |
| `app/progress/` | `src/pages/ProgressPage.tsx` | `implemented` | 深色标题带 + CEFR journey + 六枚成就；CEFR / 错误类型 / 场景 / 轮数为真实值 |
| `app/login/` | `src/pages/LoginPage.tsx` | `implemented` | 左品牌面板 + 右表单卡 |
| `app/register/` | `src/pages/RegisterPage.tsx` | `implemented` | 同上，沿用「先建号再登录」流程 |
| `app/verify-email/` | `src/pages/VerifyEmailPage.tsx` | `implemented` | 验证码页 |
| `app/forgot-password/` | `src/pages/ForgotPasswordPage.tsx` | `implemented` | 找回密码页 |
| `app/reset-password/` | `src/pages/ResetPasswordPage.tsx` | `implemented` | 重置密码页 |
| `app/layout.tsx`（navbar/footer） | `src/components/{Navbar,Footer,AppShell}.tsx` | `implemented` | `App.tsx` 用 pathless layout route 包住全部 11 条路由 |
| — | `src/pages/HistoryDetailPanel` 所在的历史详情侧板 | `implemented` | EchoWhale 独有，原型无对应 screen；本批按新设计语言重做 |
| — | `src/pages/StartupLoadingPage` 的 202 排队 / 超时 / 不支持图片三条错误路径 | `implemented` | EchoWhale 独有 |

## Component Mapping

| 原型组件 | Frontend target | 状态 | 说明 |
| --- | --- | --- | --- |
| `ui.tsx` `PageShell` / `Eyebrow` / `SectionTitle` | `src/components/ui.tsx` | `implemented` | 同名单文件原语集合，另含 `ScoreRing` / `RadarChart` |
| （无，本批新增） | `src/components/HomeComposer.tsx` / `ImageDropzone.tsx` | `implemented` | 首页双 tab 壳与拖拽上传 |
| `AuthShell.tsx` | `src/components/AuthLayout.tsx` + `AuthBrandPanel` / `AuthFormCard` / `AuthTextField` / `AuthAlert` / `AuthSubmitButton` / `AuthControls` / `AuthFeatureList` | `implemented` | 拆成 7 个原语；props 与原中文 label 全部保留 |
| — | `src/components/QuickReplyChips.tsx` / `PhraseBank.tsx` / `SessionMeter.tsx` / `SpeakButton.tsx` | `implemented` | 练习页新增；`SpeakButton` 在 `speechSynthesis` 缺失时返回 `null` |
| — | `src/hooks/useSpeechSynthesis.ts` | `implemented` | TTS 跟读，守 `window.speechSynthesis` 缺失 |
| （历史映射）`Component/UploadSceneCard` / `FeatureStrip` / `SceneMiniHeader` / `WhaleLaunchCard` / `DialogBubble` / `VoiceDock` / `LiveHintCard` / `ReviewHero` / `ReviewMetricCard` / `AuthPanel` / `AuthAside` | — | `historical` | 属于 `designs/echowhale-mvp.pen` 时代，本批未回写 `.pen` |
| （历史映射）`Component/HistoryList` / `HistoryDetailPanel` | `src/components/HistoryList.tsx`、`HistoryDetailPanel.tsx` | `implemented` | 路径与导出名沿用，视觉按新语言重做 |

## 回写规则

- Pencil 工作流已退役（2026-10-11），`designs/` 与 `docs/control/pencil-workflow.md`
  均已删除；不存在 `.pen` 回写环节。历史映射条目仅作考古参考。
- 当前端只发生小样式调整时，直接改代码即可；设计语义的变更以原型
  （仓库外）为对照，在本文件同步更新映射行。

## 当前实现说明

- 样式层已从 `tokens / base / components` 三层旧结构收敛为
  `theme / foundations / utilities` 三个文件 + Tailwind preflight，
  `src/styles.css` 只剩 4 行 import。
- 全站可访问名由 role + accessible name 驱动，次要语言文本一律置于
  `aria-hidden="true"` 的 span；页面标题用 `sr-only` + `aria-hidden` 配对。
- 原型中的编造数字（`4.9 ★`、`12,400+ learners`、`38%`、`6 min`）已删除；
  后端无数据源的区块显示 `0` / `—` / 空态，并在界面上注明缺失。
