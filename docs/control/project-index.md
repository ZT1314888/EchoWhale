# EchoWhale Docs Control Plane

这份索引页是文档工作台，不是产品说明页。它只记录当前工作流状态、下一步门槛和归档位置，方便后续 agent 和人类快速接手。

## 当前总态

- `system`: `integrating`
- 真实仓库状态：`api/` 后端 scaffold 已经成型，`frontend/` 和 `tests/` 仍以骨架为主
- 当前策略：先用 feature 文档拆 backend-heavy 主链路，再逐步推进模块测试和系统集成

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

## 模块看板

| Area | Docs Path | Current Status | Exit Gate | Merge Target | Notes |
| --- | --- | --- | --- | --- | --- |
| `platform_foundation` | `docs/modules/platform_foundation/status.md` | `building` | `module_test_passed` | `integration/system` | `ApiResponse` 与全局异常处理已落地，`/api/v1/*` 统一响应壳已形成，`/health` 保持裸探针 |
| `auth` | `docs/modules/auth/status.md` | `module_test_passed` | `module_test_passed` | `integration/system` | 邮箱密码登录、create-only 注册、refresh cookie、前端登录态恢复和 `/history` 登录守卫已落地；当前剩余 OAuth、邮箱验证与匿名数据绑定策略 |
| `media_upload` | `docs/modules/media_upload/status.md` | `building` | `module_test_passed` | `integration/system` | 上传/查询/access-url 接口、PG 持久化、统一响应壳与前端 loading 真上传桥接已落地；当前功能剩余真实私有 R2 联调、签名 URL 访问确认与密钥轮换 |
| `scene_engine` | `docs/modules/scene_engine/status.md` | `building` | `module_test_passed` | `integration/system` | `api/modules/scene_engine/` 已存在 |
| `coach_engine` | `docs/modules/coach_engine/status.md` | `building` | `module_test_passed` | `integration/system` | `api/modules/coach_engine/` 已存在 |
| `feedback_engine` | `docs/modules/feedback_engine/status.md` | `building` | `module_test_passed` | `integration/system` | `api/modules/feedback_engine/` 已存在 |
| `session_orchestration` | `docs/modules/session_orchestration/status.md` | `building` | `module_test_passed` | `integration/system` | start/get/reply/review API、session/message/review 数据库存储与前端真实练习链路已落地；当前剩余 voice 与系统级联调 |
| `history_review` | `docs/modules/history_review/status.md` | `building` | `module_test_passed` | `integration/system` | history 列表/详情与练后 review 读取已落地，并已切到真实登录用户范围；当前剩余分页和 richer review 策略 |
| `frontend_app` | `docs/modules/frontend_app/status.md` | `building` | `module_test_passed` | `integration/system` | 七页路由壳层已落地，首页选图会走真实 upload + session + review/history；登录注册、refresh 恢复、昵称菜单与 history 守卫已切真 |
| `infra_delivery` | `docs/modules/infra_delivery/status.md` | `planned` | `module_test_passed` | `integration/system` | `infra/` 仍以预留结构为主 |

## 模块清单

| Module | Owner File | Status | Branch Hint | Focus |
| --- | --- | --- | --- | --- |
| `platform_foundation` | `api/main.py`, `api/core/`, `api/common/` | `building` | `module/platform_foundation` | 启动、配置、公共依赖、共享能力 |
| `auth` | `api/routes/v1/auth.py`, `api/services/auth_service.py`, `api/db/auth_db.py` | `module_test_passed` | `module/auth` | 认证、登录态恢复、身份依赖与 owner 边界 |
| `media_upload` | `api/models/media_model.py`, `api/db/media_db.py`, `api/integrations/storage/` | `building` | `module/media_upload` | 图片上传、媒体元数据、对象存储 URL |
| `scene_engine` | `api/modules/scene_engine/` | `building` | `module/scene_engine` | 场景理解、角色设定、开场白 |
| `coach_engine` | `api/modules/coach_engine/` | `building` | `module/coach_engine` | 多轮追问、角色一致性、回复生成 |
| `feedback_engine` | `api/modules/feedback_engine/` | `building` | `module/feedback_engine` | 语法纠错、自然表达、词汇建议 |
| `session_orchestration` | `api/modules/session_engine/`, `api/services/`, `api/routes/` | `building` | `module/session_orchestration` | 会话编排、状态推进、模块串联 |
| `history_review` | `api/models/session_model.py`, `api/db/session_db.py`, `api/routes/v1/history.py` | `building` | `module/history_review` | 历史查看、回放和复盘 |
| `frontend_app` | `frontend/` | `building` | `module/frontend_app` | 上传页、练习页、历史页与 loading 真上传桥接 |
| `infra_delivery` | `infra/` | `planned` | `module/infra_delivery` | 部署、环境、交付流程 |

## 关键 Feature

| Feature | Scope | Status | Exit Gate | Merge Target |
| --- | --- | --- | --- | --- |
| 图片上传 | `media_upload` | `in_progress` | `feature_test_passed` | `module/media_upload` |
| 场景理解 | `scene_engine` | `planned` | `feature_test_passed` | `module/scene_engine` |
| 对话教练 | `coach_engine` | `planned` | `feature_test_passed` | `module/coach_engine` |
| 学习反馈 | `feedback_engine` | `planned` | `feature_test_passed` | `module/feedback_engine` |
| 会话编排 | `session_orchestration` | `in_progress` | `feature_test_passed` | `module/session_orchestration` |
| 历史查看 | `history_review` | `in_progress` | `feature_test_passed` | `module/history_review` |

## 测试门

| Test Layer | What to Prove | Status | Exit Criteria |
| --- | --- | --- | --- |
| smoke | 应用能启动，`/health` 可用 | `planned` | 入口稳定，基础路由正常 |
| module | 每个 engine 的输入输出契约稳定 | `planned` | 模块级单测通过 |
| integration | 上传 -> 会话 -> 多轮对话 -> 反馈 -> 历史 | `building` | 主链路可跑通 |
| full_flow | 前后端联通并可演示 | `planned` | `system` 可切到 `releasable` |

## 合并规则

- `feature_test_passed` 后才允许进入 `merged_to_module`
- `module_test_passed` 后才允许进入 `merged_to_integration`
- `full_flow_test_passed` 后才允许标记 `releasable`
- 若文档与代码不一致，优先改这里，再改各自 subtree 的模板

## 目前优先级

1. 补 `upload -> session -> review -> history` 的认证态系统联调
2. 再补 feature、module、system 三层测试记录
3. 最后补版本归档，让 `system` 从 `integrating` 走到 `full_flow_test_passed`
