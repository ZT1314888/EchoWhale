# Feature: `frontend_design_port`

## 基本信息

- `feature`: `frontend_design_port`
- `status`: `feature_test_passed`
- `branch`: `feature/ui-system-migration`
- `module`: `frontend_app`
- `cross_module`: `no`
- `owner`: `lucky`
- `updated_at`: `2026-10-11`
- `merge_target`: `module/frontend_app`

## 背景

EchoWhale 前端此前是**三套视觉并存**：5 个页面挂在 `BrandHeader` + `page-shell` +
`panel-card` 这套旧壳层上（由 1,739 行 `components.css` 承载），3 个认证页用较新的
`auth-modern.css`，另有 3 个页面完全定制。三者之间没有共享的导航与页脚，`/` 只是
一个孤立上传页，同一类卡片在两页里的圆角、投影和间距都不一致。

用户下载了一份 Next.js 原型（`english-oral-practice-app`）作为新设计语言，要求把
EchoWhale 前端的页面与交互整套切过去。原型带来的不只是配色，而是一整套统一语言：
cream paper `#f4f3ef` + ink `#131311` + iris `#4f46e5` + lime `#d8f34e`、
`rounded-[28px]` 卡片、Space Grotesk 标题 + Fraunces 斜体点缀的中英混排、全局
navbar/footer，以及把营销 hero 与创作器合一的首页。

**本批真源**：`C:\Users\lucky\Downloads\english-oral-practice-app`（作者本机下载的
Next.js 原型，**未纳入本仓库版本控制**）。仓库内没有该原型的副本，实现或复核时需要
在作者本机按此路径查看；对照物是原型的 `src/app/globals.css`（200 行设计令牌 +
plain-CSS 工具类）与 `src/components/ui.tsx`。

**本批明确跳过 Pencil-first 流程**（用户决定），因此本文档取代
`pencil_first_frontend_workflow` 作为本轮前端设计的真源说明。Pencil 工作流本身没有
被废除，只是本轮不适用，详见 `docs/control/pencil-workflow.md` 的 superseded 说明。

## 用户故事

- 当我打开 EchoWhale 的任意页面
- 我希望看到的是同一套视觉语言下的产品界面，而不是三个年代拼起来的页面
- 这样我就不会在首页、认证页和练习页之间反复重新认识一次「这个产品长什么样」

- 当我练习完一轮回到首页或进度页
- 我希望看到的数字都来自后端真实数据，没有数据的地方就诚实地空着
- 这样我就不会对着一个编造出来的「4.9 ★」或「12,400 名学员」判断自己的水平

## 范围

### In scope

- **C1 地基**：安装 `lucide-react`；`index.html` 换 Inter / Space Grotesk / Fraunces
  字体；新增 `theme.css`（`@theme` 令牌块）、`foundations.css`（html/body/滚动条/
  `:focus-visible`/range/reduced-motion）、`utilities.css`（原型的 plain-CSS 工具类与
  keyframes）。本 commit 零 JSX 改动。
- **C2 全局壳层**：新增 `Navbar` / `Footer` / `AppShell` / `ui.tsx` 原语集合；`App.tsx`
  加 pathless layout route 包住全部 11 条应用路由；删 `BrandHeader`；把 1,250 行的
  `App.test.tsx` 按页面拆成 `HistoryPage.test.tsx` / `ProgressPage.test.tsx` /
  `PostPracticeReviewPage.test.tsx`。
- **C3 首页**：重写 `HomeUploadPage`（hero + 二合一创作器 + 最近练习栏）、新增
  `HomeComposer` / `ImageDropzone`、重写 `SampleSceneCard`、删 `UserMenu`。
- **C4 分析等待页**：重写 `StartupLoadingPage`，`StartupAnalysisOrb` 换 iris/lime 配色。
- **C5 认证页**：重写 `AuthLayout` / `AuthBrandPanel` / `AuthFormCard` / `AuthTextField` /
  `AuthAlert` / `AuthSubmitButton` + 5 个认证页 + 登录成功提示；删 `auth-modern.css`
  (544 行) 与 `flash-toast.css` (52 行)。
- **C6a 练习页**：重写 `PracticeSessionPage`；新增 `QuickReplyChips` / `PhraseBank` /
  `SessionMeter` / `SpeakButton` / `useSpeechSynthesis`（各带测试）；`TextComposer` /
  `TurnFeedbackCard` 换肤。**不碰 `useDeepgramVoiceAgent`**。
- **C6b 复盘与历史**：重写 `PostPracticeReviewPage`（新增逐字稿 tab + 游标「加载更早
  消息」）、`HistoryPage`、`HistoryList`、`HistoryDetailPanel`；新增 `historyStats.ts`。
- **C6c 进度页**：重写 `ProgressPage`；新增 `progressStats.ts` 与 `MedalGrid`。
- **C7 删旧 CSS**：删 `tokens.css` / `base.css` / `components.css` 及对应 import，
  `styles.css` 收敛为 4 行。
- **C8 治理收口**：本文档 + 5 份既有文档改点 + `agent-control-plane.json`。

### Out of scope

- `useDeepgramVoiceAgent.ts` / `Logo.jsx` / `src/services/` / `src/types/app.ts` 的
  内部逻辑（仅按需新增类型）。
- `/session/:sessionId` 对已完成会话的重定向（见「已知缺口」R9）。
- 后端 API 与契约的任何改动：本批 9 个 commit 对 `api/` 零 diff。
- Pencil 设计资产的回写（本轮跳过 Pencil-first，见「已知缺口」）。

## 设计要点

- 关键流程：原型 `globals.css` + `ui.tsx` → 逐字移植为 `theme.css` / `foundations.css` /
  `utilities.css` 与 EchoWhale 版 `ui.tsx` → 逐页重写 → 删旧 CSS。
- 依赖模块：仅 `frontend_app`。契约面（`SessionResponse` / `SessionReviewResponse` /
  `LearnerProfileResponse`）保持不变，本批未新增任何后端字段。
- **可访问名契约（本批最重要的硬规则）**：测试由 role + accessible name 驱动，共 188 条。
  次要语言文本一律放进 `aria-hidden="true"` 的 span，绝不污染可访问名；页面标题用
  `sr-only`（放精确中文原文）+ `aria-hidden`（放可见的英文标题行）配对。若把
  `Log in · 登录` 直接写成按钮文本，可访问名会变成 `Log in 登录`，全部精确匹配断言
  当场失效。唯一仍使用 `data-testid` 的地方是没有 role/name 可依据的元素
  （`session-aside` / `session-conversation-panel` / `turn-feedback-card` /
  `message-feedback-card` / `coach-stream-bubble` / `learner-live-bubble` /
  `history-detail` / `text-composer`）。
- **数据诚实规则**：原型 hero 里的 `4.9 ★`、`12,400+ learners`、`38%`、`6 min` 是
  编造的社会证明，**直接删除**而非显示为 `—`；mock 数据一律换真实数据，没有数据源的
  区块按设计稿做出来但显示 `0` / `—` / 空态，并在界面上说明原因（如「后端不提供维度
  评分，这一格保持空态」「五维雷达需要评分数据，后端暂未提供」）。`MedalGrid` 的六个
  成就里只有「首次开口」「十轮练习」能由 `practicedTurnCount` 真实支撑，其余四个保持
  永久锁定并写出缺失字段名。
- **层叠契约（易被「清理」掉）**：`utilities.css` 里的 plain-CSS 类**故意不带
  `@layer`**，从而胜过 Tailwind 自己 `@layer utilities` 里的同名工具类。这对
  `.font-display` 是承重的——它需要额外加 `letter-spacing: -0.03em`。**不要把它挪进
  `@layer components`**，那会静默丢掉字距且没有任何测试会失败。
- 失败时如何处理：沿用既有各页错误态，不新增降级路径。

## 验收标准

- `[x]` `styles.css` 收敛为 4 行 import，`tokens.css` / `base.css` / `components.css`
  三个文件被删除，构建产物里不再出现任何一个旧选择器
- `[x]` 11 条路由全部挂在 `AppShell` 下，共用 navbar/footer
- `[x]` 11 个页面在原路径、原导出名、原 props 下完成重写，另加 6 个共享组件
  （`SampleSceneCard` / `HistoryList` / `HistoryDetailPanel` / `TextComposer` /
  `TurnFeedbackCard` / `StartupAnalysisOrb`）与 6 个既有 `Auth*` 原语换肤
- `[x]` 逐字保留约 113 条测试依赖的可访问名，测试总数从 119 增至 188
- `[x]` 原型里所有编造数字被删除或改为空态并注明原因
- `[x]` 屏幕宽度 ≤768px 时 navbar 折叠为汉堡菜单、Footer 堆叠、各页单列
- `[x]` `npm run lint` / `typecheck` / `test` / `coverage` / `build` 全绿
- `[x]` 仓库级 `ruff` / `black` / `agent_ops check` 全绿

## 测试记录

- 主要测试命令（均在 `frontend/` 下）：
  - `npm run lint`、`npm run typecheck`
  - `npm test` → **188 passed / 31 files**
  - `npm run coverage` → **90.00 / 82.92 / 85.27 / 90.00**（阈值 76/74/78/76）
  - `npm run build` → 产物 CSS 58.7 kB（迁移前 83.2 kB）
- `feature_test_passed` 的证据：上述五个前端门禁在 C7 之后全绿；仓库级
  `uv run ruff check .`、`uv run black --check .`、`uv run python -m tools.agent_ops check`
  全绿；`api/` 零 diff。
- 删除门禁（C7 的核心风险控制）：对 `components.css` 的 171 个顶层类名逐个
  grep `src/**/*.{tsx,ts,jsx}`，164 个零引用为真孤儿；7 个命中里 6 个是
  `data-testid` 值或注释里的巧合同形词，唯一真实消费者是
  `src/auth/RequireAuth.tsx` 的 `.empty-stage`，已就地改为等价 Tailwind。
  另补回 `base.css` 提供的 `button:not(:disabled) { cursor: pointer }`——Tailwind v4
  preflight 不含这条，删库会静默丢掉指针形态。
- 新增测试文件：`historyStats.test.ts`(15)、`progressStats.test.ts`(8)、
  `MedalGrid.test.tsx`(3)、`useSpeechSynthesis.test.ts`、`SessionMeter.test.tsx`、
  `SpeakButton.test.tsx`、`PhraseBank.test.tsx`、`QuickReplyChips.test.tsx`、
  `Navbar.test.tsx` 等；`HistoryPage.test.tsx`(2→5)、
  `PostPracticeReviewPage.test.tsx`(3→6)、`ProgressPage.test.tsx`(3→5)、
  `TextComposer.test.tsx`(4→6，组件达 100%)。
- 已知缺口：
  - **R9：`/session/:sessionId` 对已完成会话仍可直接进入**。原型会重定向到复盘页，
    EchoWhale 不会；加重定向会破坏现有练习页测试，本批**未加**，记为后续项。
  - **R8：练习页布局需人工冒烟**。68px sticky navbar 叠加原全高舞台，`min-height` /
    `overflow` 的双滚动条风险不在 5 条练习测试的覆盖范围内；`AppShell` 已在
    session 路由抑制 Footer，但实际观感需人工走查。
  - **11 条路由 × 3 个错误/空态的人工走查**（计划里的端到端清单）尚未执行，需后端在
    `VITE_API_PROXY_TARGET` 跑着时进行。
  - Pencil 设计资产未回写，`designs/echowhale-mvp.pen` 停留在本批之前的状态。

## 控制面同步

- 已在 `docs/control/agent-control-plane.json` 登记本 feature（`feature_test_passed`，
  `merge_target: module/frontend_app`），并更新 `frontend_app` 模块 notes 与
  `latest_snapshot`。
- 同步后运行：`uv run python -m tools.agent_ops render`
- 校验：`uv run python -m tools.agent_ops check`

## 合并与关闭

- 何时可以写成 `merged_to_module`：本分支合入 `integration/system` 之后。
- 何时可以写成 `closed`：上述人工走查清单执行完、R9 与 Pencil 回写各自处置完之后。
- 相关文档链接：
  - `docs/modules/frontend_app/design_mapping.md`（本批重建的设计映射表）
  - `docs/control/pencil-workflow.md`（superseded 说明）
  - `docs/modules/frontend_app/status.md`
  - 提交范围：`feature/ui-system-migration` 上 C1–C8 共 10 个 commit
    （`957a93c` 起；代码部分 C1–C7 为 73 文件、+4,950 / −3,835 行，C8 只改文档）
