# EchoWhale Docs Control Plane

这份索引页是文档工作台，不是产品说明页。它只记录当前工作流状态、下一步门槛和归档位置，方便后续 agent 和人类快速接手。

## 当前总态

- `system`: `idle`
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
| `platform_foundation` | `docs/modules/platform_foundation/status.md` | `building` | `module_test_passed` | `integration/system` | 公共底座和入口已存在，但仍需模块级约束与验证 |
| `media_upload` | `docs/modules/media_upload/status.md` | `building` | `module_test_passed` | `integration/system` | 媒体模型、存储 URL 骨架已在，上传链路未闭环 |
| `scene_engine` | `docs/modules/scene_engine/status.md` | `building` | `module_test_passed` | `integration/system` | `api/modules/scene_engine/` 已存在 |
| `coach_engine` | `docs/modules/coach_engine/status.md` | `building` | `module_test_passed` | `integration/system` | `api/modules/coach_engine/` 已存在 |
| `feedback_engine` | `docs/modules/feedback_engine/status.md` | `building` | `module_test_passed` | `integration/system` | `api/modules/feedback_engine/` 已存在 |
| `session_orchestration` | `docs/modules/session_orchestration/status.md` | `building` | `module_test_passed` | `integration/system` | `api/modules/session_engine/` 已存在 |
| `history_review` | `docs/modules/history_review/status.md` | `planned` | `module_test_passed` | `integration/system` | 数据模型与会话存储已在，查询链路未形成 |
| `frontend_app` | `docs/modules/frontend_app/status.md` | `planned` | `module_test_passed` | `integration/system` | `frontend/` 仍是目录骨架 |
| `infra_delivery` | `docs/modules/infra_delivery/status.md` | `planned` | `module_test_passed` | `integration/system` | `infra/` 仍以预留结构为主 |

## 模块清单

| Module | Owner File | Status | Branch Hint | Focus |
| --- | --- | --- | --- | --- |
| `platform_foundation` | `api/main.py`, `api/core/`, `api/common/` | `building` | `module/platform_foundation` | 启动、配置、公共依赖、共享能力 |
| `media_upload` | `api/models/media_model.py`, `api/db/media_db.py`, `api/integrations/storage/` | `building` | `module/media_upload` | 图片上传、媒体元数据、对象存储 URL |
| `scene_engine` | `api/modules/scene_engine/` | `building` | `module/scene_engine` | 场景理解、角色设定、开场白 |
| `coach_engine` | `api/modules/coach_engine/` | `building` | `module/coach_engine` | 多轮追问、角色一致性、回复生成 |
| `feedback_engine` | `api/modules/feedback_engine/` | `building` | `module/feedback_engine` | 语法纠错、自然表达、词汇建议 |
| `session_orchestration` | `api/modules/session_engine/`, `api/services/`, `api/routes/` | `building` | `module/session_orchestration` | 会话编排、状态推进、模块串联 |
| `history_review` | `api/models/session_model.py`, `api/db/session_db.py` | `planned` | `module/history_review` | 历史查看、回放和复盘 |
| `frontend_app` | `frontend/` | `planned` | `module/frontend_app` | 上传页、练习页、历史页 |
| `infra_delivery` | `infra/` | `planned` | `module/infra_delivery` | 部署、环境、交付流程 |

## 关键 Feature

| Feature | Scope | Status | Exit Gate | Merge Target |
| --- | --- | --- | --- | --- |
| 图片上传 | `media_upload` | `planned` | `feature_test_passed` | `module/media_upload` |
| 场景理解 | `scene_engine` | `planned` | `feature_test_passed` | `module/scene_engine` |
| 对话教练 | `coach_engine` | `planned` | `feature_test_passed` | `module/coach_engine` |
| 学习反馈 | `feedback_engine` | `planned` | `feature_test_passed` | `module/feedback_engine` |
| 会话编排 | `session_orchestration` | `planned` | `feature_test_passed` | `module/session_orchestration` |
| 历史查看 | `history_review` | `planned` | `feature_test_passed` | `module/history_review` |

## 测试门

| Test Layer | What to Prove | Status | Exit Criteria |
| --- | --- | --- | --- |
| smoke | 应用能启动，`/health` 可用 | `planned` | 入口稳定，基础路由正常 |
| module | 每个 engine 的输入输出契约稳定 | `planned` | 模块级单测通过 |
| integration | 上传 -> 会话 -> 多轮对话 -> 反馈 -> 历史 | `planned` | 主链路可跑通 |
| full_flow | 前后端联通并可演示 | `planned` | `system` 可切到 `releasable` |

## 合并规则

- `feature_test_passed` 后才允许进入 `merged_to_module`
- `module_test_passed` 后才允许进入 `merged_to_integration`
- `full_flow_test_passed` 后才允许标记 `releasable`
- 若文档与代码不一致，优先改这里，再改各自 subtree 的模板

## 目前优先级

1. 先把 backend-heavy 主链路拆成可执行 feature 文档
2. 再补 feature、module、system 三层测试记录
3. 最后补版本归档，让 `system` 从 `integrating` 走到 `full_flow_test_passed`
