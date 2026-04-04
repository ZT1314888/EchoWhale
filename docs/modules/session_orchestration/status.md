# Module Status: `session_orchestration`

## 基本信息

- `module`: `session_orchestration`
- `status`: `building`
- `branch`: `module/session_orchestration`
- `owner`: `codex`
- `updated_at`: `2026-04-04`

## 模块目标

串联 scene、coach、feedback 三个模块，管理会话状态、消息聚合与主链路推进。

## 当前真相

- 现有实现：`api/modules/session_engine/`、`api/db/session_db.py`、`api/routes/v1/sessions.py`
- 已完成边界：`start/get/reply/review` 主链路已落地，session/message/review 已切到数据库持久化，前端上传成功后会创建真实 session 并进入真实练习页
- 已完成边界：session 创建前仍会校验媒体必须为 `uploaded`，场景分析继续通过签名 URL 读取媒体对象
- 已完成边界：history 列表与详情读取接口已落地，前端 `PostPracticeReview` / `History` 已切到真实后端读取
- 已完成边界：已修复 session 初始 opener 持久化时的父子写入顺序问题，`POST /api/v1/sessions` 不再因 `session_messages_session_id_fkey` 在严格 FK 数据库下报错
- 仍然缺失：认证态用户归属、跨模块更完整的系统级联调、语音 session 分支

## 输入输出契约

- 输入：`user_id`、`media_id`、学习者回复、历史会话上下文
- 输出：会话对象、状态推进、消息聚合结果
- 关键字段：`session_id`、`status`、`messages`

## 代码位置

- `api/modules/session_engine/`
- `api/db/session_db.py`
- `api/routes/v1/sessions.py`

## 当前工作

- `[x]` 明确 start/get/reply 三条主链路
- `[x]` 落数据库 session/message repository 与迁移脚本
- `[x]` 补 session API 与模块级最小测试
- `[x]` 对接 history/review 查询链路
- `[x]` 收口 reply 原子更新与空输入校验
- `[x]` 修复 session 首条 message 在 FK 严格数据库下的持久化顺序 bug
- `[ ]` 做更完整的前后端系统联调

## 测试门

- `module_test_passed` 的标准：会话启动、快照读取、回复推进、review/history 读取可稳定验证
- 已覆盖：session repository 持久化、session API start/get/reply/review、history 列表与详情、媒体状态保护、session 签名 URL 消费、reply 原子更新、严格 FK 模式下的 session 初始 message 持久化回归
- 还没覆盖的风险：真实用户鉴权、跨模块系统级联调、语音 session 分支

## 阻塞项

- 当前仍使用 `default_user_id`，未进入真实鉴权流
- 真实文本主链路已闭环，但 `upload -> session -> history` 的系统级联调还需与真实 R2 结果一起收口

## 变更记录

- `2026-03-30`：初始化模块状态文档
- `2026-04-03`：新增 session repository、数据库迁移与 `/api/v1/sessions` start/get/reply 路由，前端练习主路径接入真实 session API
- `2026-04-04`：新增 `/api/v1/sessions/{session_id}/review` 与 `/api/v1/history/sessions*`，补 session review 持久化、reply 原子更新、前端 review/history 切真
- `2026-04-04`：修复 `save_session()` 在 FK 严格数据库下先写 `session_messages` 的顺序 bug，补强 FK 回归测试与 PostgreSQL 定向验证
