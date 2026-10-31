# EchoWhale Docs Control Plane

这份索引页是文档工作台，不是产品说明页。它只记录当前工作流状态、下一步门槛和归档位置，方便后续 agent 和人类快速接手。

以下带标记的生成区块以 `docs/control/agent-control-plane.json` 为单一事实源。调整模块/feature/测试层状态时，先改事实源，再运行 `uv run python -m tools.agent_ops render`。

<!-- agent-control:generated:start -->
## 当前总态

- `system`: `integrating`
- 真实仓库状态：`api/` 后端与 backend-heavy 测试已成型，`frontend/` 已整套切到原型设计语言并补齐进度页，`infra/` 仍以预留结构为主。
- 当前策略：先稳住 agent 控制面一致性与层级验证记录，再继续推进真实联调和系统级 smoke。

## 最新进度快照

- 最新归档：`docs/features/frontend_design_port/feature.md`
- 本轮结论：前端 UI 整套迁移至 english-oral-practice-app 原型设计语言（C1–C8 十个 commit，分支 feature/ui-system-migration）。C1：装 lucide-react、换 Inter/Space Grotesk/Fraunces 字体、新增 theme.css(@theme 令牌)/foundations.css/utilities.css 三份新样式。C2：新增 Navbar/Footer/AppShell/ui.tsx，App.tsx 加 pathless layout route 包住全部 11 条路由，删 BrandHeader，并把 1,250 行 App.test.tsx 按页拆成三份。C3–C6c：在保留 Deepgram 实时语音的前提下逐页重写首页(二合一创作器)/分析等待页/5 个认证页/练习页(叠加 TTS 跟读、快捷回复、金句锦囊、计时器)/复盘页(新增逐字稿 tab + 游标分页)/历史页(搜索筛选排序)/进度页(CEFR journey + 成就墙)，新增 HomeComposer/ImageDropzone/QuickReplyChips/PhraseBank/SessionMeter/SpeakButton/MedalGrid/useSpeechSynthesis/historyStats/progressStats。C7：删 tokens.css/base.css/components.css 及 C5 已删的 auth-modern.css/flash-toast.css 共 2,395 行，styles.css 收敛为 4 行 import。C8：本文档与 5 份治理文档收口。api/ 与前端契约（SessionResponse/SessionReviewResponse/LearnerProfileResponse）零 diff。
- 当前主要阻塞：无新增阻塞。frontend_design_port 的四项遗留（R9 重定向、R8 练习页冒烟、11 路由错误/空态人工走查、Pencil 资产处置）已在收口批次全部完成：R9 已实现（SessionSummary 补 status 映射，测试 188→189）；R8 与走查通过（证据见任务 .trellis/tasks/10-11-ui-migration-closeout/）；Pencil 整体退役，designs/ 与 pencil 相关文档已删除。剩余唯一事项：feature/ui-system-migration 合入 integration/system 后写 merged_to_module。
- 补充进展：两套设计源并存风险已收口：design_mapping.md 顶部加指向说明并重建全表（历史条目标 historical）、control/pencil-workflow.md 与 pencil_first_frontend_workflow/feature.md 标记 superseded（保留不删）、frontend_production_shell/feature.md 加后续状态说明。前端门禁：lint 零输出、typecheck 绿、vitest 188 passed / 31 files（迁移前 119）、coverage 90.00/82.92/85.27/90.00 全过阈值 76/74/78/76、build 产物 CSS 从 83.2 kB 降到 58.7 kB；仓库级 ruff / black / agent_ops check 全绿；api/ 零 diff。迁移的承重约束是「只坏 5 个测试而不是 55 个」：测试由 role + accessible name 驱动，本次是纯视觉变更，约 113 条测试靠逐字保留可访问名原样通过——次要语言文本一律置于 aria-hidden 的 span（否则 Log in · 登录 会把可访问名污染成 Log in 登录，全部精确匹配断言失效），页面标题用 sr-only(精确中文)+aria-hidden(可见英文行)配对。删除门禁：对 components.css 的 171 个顶层类名逐个 grep src/**/*.{tsx,ts,jsx}，164 个零引用为真孤儿，7 个命中里 6 个是 data-testid 值或注释里的巧合同形词，唯一真实消费者是 auth/RequireAuth.tsx 的 .empty-stage（已就地改为等价 Tailwind）。另补回 base.css 提供的 button:not(:disabled){cursor:pointer}——Tailwind v4 preflight 不含此条，删库会静默丢掉指针形态，而 :not(:disabled) 保住 disabled:cursor-not-allowed 不被无 layer 规则盖过。数据诚实：原型 hero 的 4.9 ★ / 12,400+ learners / 38% / 6 min 直接删除而非显示占位；无后端数据源的区块显示 0 / — / 空态并注明原因（如「后端不提供维度评分，这一格保持空态」）；MedalGrid 六枚成就里只有首次开口与十轮练习由 practicedTurnCount 真实支撑，其余四枚永久锁定并写出缺失字段名。层叠契约：utilities.css 的 plain-CSS 类故意不带 @layer 以胜过 Tailwind 同名工具类，.font-display 的 letter-spacing:-0.03em 依赖这一点，挪进 @layer components 会静默丢字距且无测试会失败。 收口批次（2026-10-11）：R9 落地——PracticeSessionPage 对 completed 会话渲染 <Navigate replace> 到 /session/:id/review，SessionSummary 增加 status 字段（api/ 零 diff），练习页测试 188→189 全绿，前端五门禁与仓库级 ruff/black/agent_ops check 全绿；R8 量化冒烟——1440×900 页面级纵向溢出 0、无横向溢出、68px navbar 下无双滚动条，375×812 汉堡折叠 + 单列 + 零横向溢出；11 条路由 × 错误/空态走查全部通过（截图证据在任务目录 evidence/）；Pencil 资产整体删除（designs/ 的 .pen/logo/assets/README、docs/control/pencil-workflow.md、docs/features/pencil_first_frontend_workflow/、两份 pencil 版本记录），README/design_mapping/status/控制面同步改写，存活文档不再把 Pencil 当作现行流程。走查顺带记录三项既有问题（练习页硬刷新 auth 竞态、dev StrictMode 双挂载 refresh 轮换竞速、练习错误卡裸露后端英文文案），均非本批引入，待后续处理。

## 模块看板

| Area | Docs Path | Current Status | Exit Gate | Merge Target | Notes |
| --- | --- | --- | --- | --- | --- |
| `platform_foundation` | `docs/modules/platform_foundation/status.md` | `building` | `module_test_passed` | `integration/system` | 应用入口、共享配置和控制面治理工具正在收口。 |
| `auth` | `docs/modules/auth/status.md` | `module_test_passed` | `module_test_passed` | `integration/system` | 邮箱密码登录、验证码激活、Redis 频控和 refresh cookie 已落地。 |
| `media_upload` | `docs/modules/media_upload/status.md` | `building` | `module_test_passed` | `integration/system` | 上传/查询/access-url 和 PG 持久化已落地，剩余真实私有 R2 联调。 |
| `scene_engine` | `docs/modules/scene_engine/status.md` | `building` | `module_test_passed` | `integration/system` | live provider 配置门禁已收紧，当前剩余真实样本评估与质量波动验证。 |
| `coach_engine` | `docs/modules/coach_engine/status.md` | `building` | `module_test_passed` | `integration/system` | 文本 provider 主备逻辑已落地，live 模式要求至少一个真实 provider。 |
| `feedback_engine` | `docs/modules/feedback_engine/status.md` | `building` | `module_test_passed` | `integration/system` | useful words 和 live client 选择逻辑已收口，仍需更多系统联调。 |
| `session_orchestration` | `docs/modules/session_orchestration/status.md` | `building` | `module_test_passed` | `integration/system` | start/get/reply/review 与 voice bootstrap/complete 已落地，剩余完整系统级联调。 |
| `history_review` | `docs/modules/history_review/status.md` | `building` | `module_test_passed` | `integration/system` | history 列表、详情和消息回放分页已落地，剩余筛选和 richer review 策略。 |
| `frontend_app` | `docs/modules/frontend_app/status.md` | `building` | `module_test_passed` | `integration/system` | 整套 UI 已迁到原型设计语言（Navbar/Footer/AppShell + theme/foundations/utilities 三份样式），11 条路由全部落地并走查通过；R9 已完成会话重定向复盘页；Pencil 设计资产已整体退役并删除。 |
| `infra_delivery` | `docs/modules/infra_delivery/status.md` | `planned` | `module_test_passed` | `integration/system` | `infra/` 仍以预留结构为主。 |

## 模块清单

| Module | Owner File | Status | Branch Hint | Focus |
| --- | --- | --- | --- | --- |
| `platform_foundation` | `api/main.py`, `api/core/`, `api/common/`, `tools/agent_ops.py` | `building` | `module/platform_foundation` | 启动、配置、共享能力、agent 协作治理 |
| `auth` | `api/routes/v1/auth.py`, `api/services/auth_service.py`, `api/db/auth_db.py` | `module_test_passed` | `module/auth` | 认证、登录态恢复、身份边界 |
| `media_upload` | `api/models/media_model.py`, `api/db/media_db.py`, `api/integrations/storage/` | `building` | `module/media_upload` | 图片上传、媒体元数据、对象存储 URL |
| `scene_engine` | `api/modules/scene_engine/` | `building` | `module/scene_engine` | 场景理解、角色设定、开场白 |
| `coach_engine` | `api/modules/coach_engine/` | `building` | `module/coach_engine` | 多轮追问、角色一致性、回复生成 |
| `feedback_engine` | `api/modules/feedback_engine/` | `building` | `module/feedback_engine` | 语法纠错、自然表达、词汇建议 |
| `session_orchestration` | `api/modules/session_engine/`, `api/services/`, `api/routes/` | `building` | `module/session_orchestration` | 会话编排、状态推进、模块串联 |
| `history_review` | `api/models/session_model.py`, `api/db/session_db.py`, `api/routes/v1/history.py` | `building` | `module/history_review` | 历史查看、回放和复盘 |
| `frontend_app` | `frontend/` | `building` | `module/frontend_app` | 上传页、练习页、历史页与真接口桥接 |
| `infra_delivery` | `infra/` | `planned` | `module/infra_delivery` | 部署、环境、交付流程 |

## 关键 Feature

| Feature | Scope | Status | Exit Gate | Merge Target |
| --- | --- | --- | --- | --- |
| 图片上传 | `media_upload` | `in_progress` | `feature_test_passed` | `module/media_upload` |
| 场景理解 | `scene_engine` | `in_progress` | `feature_test_passed` | `module/scene_engine` |
| 对话教练 | `coach_engine` | `in_progress` | `feature_test_passed` | `module/coach_engine` |
| 学习反馈 | `feedback_engine` | `in_progress` | `feature_test_passed` | `module/feedback_engine` |
| 会话编排 | `session_orchestration` | `in_progress` | `feature_test_passed` | `module/session_orchestration` |
| 历史查看 | `history_review` | `in_progress` | `feature_test_passed` | `module/history_review` |
| 文字回复流式 | `text_reply_streaming` | `feature_test_passed` | `feature_test_passed` | `module/session_orchestration` |
| 场景分析缓存 | `scene_analysis_caching` | `feature_test_passed` | `feature_test_passed` | `module/scene_engine` |
| 前端流式与轮询接线 | `frontend_stream_ui_wiring` | `feature_test_passed` | `feature_test_passed` | `module/frontend_app` |
| 前端质量门禁 | `frontend_quality_gates` | `feature_test_passed` | `feature_test_passed` | `module/frontend_app` |
| 等待体验与反馈统一 | `frontend_wait_ux_feedback_unification` | `feature_test_passed` | `feature_test_passed` | `module/frontend_app` |
| CI 覆盖率与 lint 门禁 | `ci_coverage_lint_gates` | `feature_test_passed` | `feature_test_passed` | `module/platform_foundation` |
| black 格式化门禁 | `black_formatting` | `feature_test_passed` | `feature_test_passed` | `module/platform_foundation` |
| 访客身份与限流加固 | `visitor_ratelimit_hardening` | `feature_test_passed` | `feature_test_passed` | `module/platform_foundation` |
| 上传流式校验与请求体大小门 | `media_upload_stream_guard` | `feature_test_passed` | `feature_test_passed` | `module/media_upload` |
| 生产配置门控反转与清单补全 | `production_config_gate` | `feature_test_passed` | `feature_test_passed` | `module/platform_foundation` |
| 会话启动媒体归属校验 | `session_media_ownership_check` | `feature_test_passed` | `feature_test_passed` | `module/session_orchestration` |
| 反馈失败降级不拖垮整轮对话 | `feedback_failure_degradation` | `feature_test_passed` | `feature_test_passed` | `module/session_orchestration` |
| 会话写路径完整性与追加语义 | `session_write_integrity` | `feature_test_passed` | `feature_test_passed` | `module/session_orchestration` |
| 限流体系收口 | `ratelimit_closing` | `feature_test_passed` | `feature_test_passed` | `module/platform_foundation` |
| LLM成本与输入边界 | `llm_cost_and_input_bounds` | `feature_test_passed` | `feature_test_passed` | `module/platform_foundation` |
| 请求关联ID与就绪探针 | `request_id_and_readiness` | `feature_test_passed` | `feature_test_passed` | `module/platform_foundation` |
| 交付门禁与部署收口 | `delivery_gates_and_deployment` | `feature_test_passed` | `feature_test_passed` | `module/infra_delivery` |
| 教学内核提示词升级与LLM复盘 | `teaching_kernel_prompts` | `feature_test_passed` | `feature_test_passed` | `module/session_orchestration` |
| 学员状态持久化与提示词动态注入 | `learner_profile_prompt_injection` | `feature_test_passed` | `feature_test_passed` | `module/session_orchestration` |
| 教练与复盘离线评测样例集 | `coach_engine` | `feature_test_passed` | `feature_test_passed` | `module/coach_engine` |
| 场景文案单一事实源与死代码清理 | `scene_copy_single_source_cleanup` | `feature_test_passed` | `feature_test_passed` | `module/frontend_app` |
| PRD 升版 v0.5 与 API 文档 | `prd_v05_api_docs` | `feature_test_passed` | `feature_test_passed` | `module/platform_foundation` |
| OTel 可观测性三层 span | `otel_engine_spans` | `feature_test_passed` | `feature_test_passed` | `module/platform_foundation` |
| 学员档案读取 API 与进度页 | `learner_profile_progress` | `feature_test_passed` | `feature_test_passed` | `module/session_orchestration` |
| 评测驱动提示词修正 | `eval_prompt_fixes` | `feature_test_passed` | `feature_test_passed` | `module/coach_engine` |
| LLM ReviewCopy 生产消费 | `review_copy_consumption` | `feature_test_passed` | `feature_test_passed` | `module/session_orchestration` |
| 后端韧性收尾批次 | `resilience_closing_batch` | `feature_test_passed` | `feature_test_passed` | `module/platform_foundation` |
| CI PG平价验证与前端eslint门禁 | `ci_pg_parity_and_eslint_gate` | `feature_test_passed` | `feature_test_passed` | `module/platform_foundation` |
| think代理令牌生命周期绑定 | `think_token_lifecycle_binding` | `feature_test_passed` | `feature_test_passed` | `module/platform_foundation` |
| PG迁移downgrade往返验证与全仓储方言参数化 | `pg_downgrade_repo_dialect_parity` | `feature_test_passed` | `feature_test_passed` | `module/platform_foundation` |
| 前端UI整套迁移至原型设计语言 | `frontend_design_port` | `feature_test_passed` | `feature_test_passed` | `module/frontend_app` |

## 测试门

| Test Layer | What to Prove | Status | Exit Criteria |
| --- | --- | --- | --- |
| smoke | 应用能启动，`/health` 可用。 | `planned` | 入口稳定，基础路由正常。 |
| module | 每个 engine 和共享底座的输入输出契约稳定。 | `building` | 模块级单测持续补齐并保持通过。 |
| integration | 上传 -> 会话 -> 多轮对话 -> 反馈 -> 历史 的 backend-heavy 主链路可跑通。 | `building` | 主链路和关键外部适配已完成系统联调。 |
| full_flow | 前后端联通并可演示。 | `planned` | `system` 可切到 `releasable`。 |
<!-- agent-control:generated:end -->

## 状态词

### feature

`planned` -> `in_progress` -> `feature_test_passed` -> `merged_to_module` -> `closed`

### module

`planned` -> `building` -> `module_test_passed` -> `merged_to_integration` -> `closed`

### system

`idle` -> `integrating` -> `full_flow_test_passed` -> `releasable`

## 分支约定

- feature 分支：`feature/<feature-name>`
- bugfix 分支：`bugfix/<bug-name>`
- module 分支：`module/<module-name>`
- 集成分支：`integration/system`
- 主线分支：`main`

分支名只带类型和 slug，不带模块段；模块归属写在 feature/bug 文档的 `module` 字段里，不在分支名中重复编码。

## 操作入口

- 校验控制面：`uv run python -m tools.agent_ops check`
- 重建索引页生成区块：`uv run python -m tools.agent_ops render`
- 新建治理文档骨架：`uv run python -m tools.agent_ops bootstrap <feature|bug|module|version> <slug>`

## 合并规则

- `feature_test_passed` 后才允许进入 `merged_to_module`
- `module_test_passed` 后才允许进入 `merged_to_integration`
- `full_flow_test_passed` 后才允许标记 `releasable`
- 若文档与代码不一致，先更新事实源和控制面，再修正文档细节

## 目前优先级

1. 补 `upload -> session -> deepgram voice -> review -> history` 的认证态系统联调
2. 持续补 feature、module、system 三层测试记录
3. 让控制面事实源、模板和 repo-local 检查命令成为默认协作入口
