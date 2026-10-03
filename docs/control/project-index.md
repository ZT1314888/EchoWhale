# EchoWhale Docs Control Plane

这份索引页是文档工作台，不是产品说明页。它只记录当前工作流状态、下一步门槛和归档位置，方便后续 agent 和人类快速接手。

以下带标记的生成区块以 `docs/control/agent-control-plane.json` 为单一事实源。调整模块/feature/测试层状态时，先改事实源，再运行 `uv run python -m tools.agent_ops render`。

<!-- agent-control:generated:start -->
## 当前总态

- `system`: `integrating`
- 真实仓库状态：`api/` 后端与 backend-heavy 测试已成型，`frontend/` 持续补齐，`infra/` 仍以预留结构为主。
- 当前策略：先稳住 agent 控制面一致性与层级验证记录，再继续推进真实联调和系统级 smoke。

## 最新进度快照

- 最新归档：`docs/features/prd_v05_api_docs/feature.md`
- 本轮结论：审计 Schedule Later 21 + Documentation 维度收口（纯文档批次，生产代码零改动）：docs/prd.md 升版 v0.5 重写当前形态——§2.3 非目标移出语音识别（保留发音打分）、§7 技术方案重写（PostgreSQL+SQLAlchemy+Alembic、Redis+RQ 双队列、mock/live 双运行时、签名访客 Cookie、Deepgram），删除“第一版允许内存存储或 mock 数据”；§4 补流式回复/语音练习/学员档案/LLM 复盘/场景文案下发/12MB 请求体门与 202；§10 验收补功能与工程门禁数字；§11 v0.1–v0.4 标注完成态 + v0.5 阶段意图四候选（档案读取 API 与进度页、ReviewCopy 生产消费、评测驱动提示词修正、OTel/Langfuse），注明 PRD 不做 changelog；修复 §7–§10 编号错位。新建 docs/api.md 十一节：认证与身份/端点清单/统一信封与错误码/限流配额（含匿名 IP 伴生键）/SSE 事件协议/202 轮询/游标分页/请求体上限与 X-Request-ID//health 与 /readyz/think 代理特例，每个可验证声明附代码出处。README 增“文档”小节三链接并补 API 概览表缺漏的 resend-verification 行。feature.md 附 10 张“声明 ↔ 代码出处”对照表（核心验收物）。
- 当前主要阻塞：无新增阻塞。教练/复盘 live 评测仍未实跑（费用与真实 provider 依赖，同前批）；评测暴露 4 项提示词疑似问题仍未改（另批）；eslint 批次、档案读取 API 与前端进度页待立项（PRD 升版与 API 文档本批已完成）。
- 补充进展：pytest 540 passed / 9 skipped，覆盖率 88.49%（门禁 87，与基线逐项一致）；ruff / black 全绿；前端 typecheck 通过、vitest 15 文件 107 passed，覆盖率 Stmts 85.97 / Branch 77.42 / Funcs 84.02 / Lines 85.97 对阈值 76/74/78/76 全部持平达标；git diff 仅 docs/** 与 README.md，生产代码零改动；核对发现 2 处清单与代码不一致（auth 端点 9 而非 8、think 白名单空值语义），均以代码为准落档。

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
| `frontend_app` | `docs/modules/frontend_app/status.md` | `building` | `module_test_passed` | `integration/system` | 七页路由壳层和真 upload/session/review/history 路径已落地。 |
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

- feature 分支：`feature/<module-name>/<feature-name>`
- bugfix 分支：`bugfix/<module-name>/<bug-name>`
- module 分支：`module/<module-name>`
- 集成分支：`integration/system`
- 主线分支：`main`

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
