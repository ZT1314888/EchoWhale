# EchoWhale Docs Control Plane

这份索引页是文档工作台，不是产品说明页。它只记录当前工作流状态、下一步门槛和归档位置，方便后续 agent 和人类快速接手。

以下带标记的生成区块以 `docs/control/agent-control-plane.json` 为单一事实源。调整模块/feature/测试层状态时，先改事实源，再运行 `uv run python -m tools.agent_ops render`。

<!-- agent-control:generated:start -->
## 当前总态

- `system`: `integrating`
- 真实仓库状态：`api/` 后端与 backend-heavy 测试已成型，`frontend/` 持续补齐，`infra/` 仍以预留结构为主。
- 当前策略：先稳住 agent 控制面一致性与层级验证记录，再继续推进真实联调和系统级 smoke。

## 最新进度快照

- 最新归档：`docs/features/frontend_quality_gates/feature.md`
- 本轮结论：第五批质量门禁落地：tsc --noEmit 清零（lib ES2022 / vite-env.d.ts / apiClient credentials as const / streamState holder 修 never 收窄 / 示例场景白名单守卫），package.json 新增 typecheck 脚本；consumeSseResponse 包 try/finally 并在退出时 reader.cancel，中途取消/断流不再泄漏读取器（含中途失败 spy 测试）；新增仓库首个 CI（backend：uv sync --frozen + sqlite 建表 + pytest；frontend：npm ci + typecheck + vitest）。CI 配方逼出并修复测试密闭性缺口：无 .env 时 38 failed（DATABASE_URL 必填 + live 用例隐式依赖本机供应商密钥），live 用例改为 dummy 槽位 monkeypatch、CI 用 sqlite + create_all 预建表，配方逐字本地验证。
- 当前主要阻塞：vitest coverage 阈值与 lint 接入 CI 待下一批；上传页真实进度与取消等待、语音回合反馈卡统一为 P1 体验项；SCENE_ANALYSIS_ASYNC_ENABLED 生产开启前确认 worker 消费；真实依赖的系统级 smoke 仍是既有主阻塞。
- 补充进展：npx tsc --noEmit 0 error（批前 13）；npx vitest run 99 passed（基线 98 + 新增 1）；uv run pytest tests 224 passed / 2 skipped（本地与模拟 CI 环境均为全绿）；uv lock --check 通过。

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
