# Module Status: `history_review`

## 基本信息

- `module`: `history_review`
- `status`: `planned`
- `branch`: `module/history_review`
- `owner`: `unassigned`
- `updated_at`: `2026-03-30`

## 模块目标

提供历史会话查看、回放、复习入口和后续复盘所需的数据读取能力。

## 当前真相

- 现有实现：`api/models/session_model.py`、`api/models/message_model.py`、`api/db/session_db.py`
- 已完成边界：会话与消息模型、会话存储骨架
- 仍然缺失：历史查询路由、复盘视图、明确的读取契约

## 输入输出契约

- 输入：用户标识、会话标识、筛选条件
- 输出：历史会话列表、单会话详情、复盘信息
- 关键字段：`session_id`、`messages`、场景、角色、反馈

## 代码位置

- `api/models/session_model.py`
- `api/models/message_model.py`
- `api/db/session_db.py`

## 当前工作

- `[ ]` 明确历史查询输出结构
- `[ ]` 设计最小回放接口
- `[ ]` 补会话读取与排序测试

## 测试门

- `module_test_passed` 的标准：历史列表和详情读取稳定可验证
- 最少要覆盖的用例：空历史、单会话详情、多会话排序
- 还没覆盖的风险：后续字段扩展导致历史结构不稳定

## 阻塞项

- 路由和前端回放入口尚未落地

## 变更记录

- `2026-03-30`：初始化模块状态文档
