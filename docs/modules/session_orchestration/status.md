# Module Status: `session_orchestration`

## 基本信息

- `module`: `session_orchestration`
- `status`: `building`
- `branch`: `module/session_orchestration`
- `owner`: `unassigned`
- `updated_at`: `2026-03-30`

## 模块目标

串联 scene、coach、feedback 三个模块，管理会话状态、消息聚合与主链路推进。

## 当前真相

- 现有实现：`api/modules/session_engine/`、`api/services/`、`api/models/session_model.py`
- 已完成边界：会话 service、agent、schema 骨架
- 仍然缺失：路由入口、历史联动、模块间契约验证

## 输入输出契约

- 输入：`user_id`、`media_id`、学习者回复、历史会话上下文
- 输出：会话对象、状态推进、消息聚合结果
- 关键字段：`session_id`、`status`、`messages`

## 代码位置

- `api/modules/session_engine/`
- `api/services/`
- `api/models/session_model.py`

## 当前工作

- `[ ]` 明确 start/reply 两条主链路
- `[ ]` 补模块串联的最小集成测试
- `[ ]` 明确会话状态与消息聚合规范

## 测试门

- `module_test_passed` 的标准：会话启动、回复推进、消息聚合可稳定验证
- 最少要覆盖的用例：start_session、reply_to_session、空会话兜底
- 还没覆盖的风险：跨模块接口变动引起的链路回退

## 阻塞项

- 路由层与历史查询尚未联通

## 变更记录

- `2026-03-30`：初始化模块状态文档
