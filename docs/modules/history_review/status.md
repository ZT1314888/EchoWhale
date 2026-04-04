# Module Status: `history_review`

## 基本信息

- `module`: `history_review`
- `status`: `building`
- `branch`: `module/history_review`
- `owner`: `unassigned`
- `updated_at`: `2026-04-04`

## 模块目标

提供历史会话查看、回放、复习入口和后续复盘所需的数据读取能力。

## 当前真相

- 现有实现：`api/models/session_model.py`、`api/models/message_model.py`、`api/models/review_model.py`、`api/db/session_db.py`、`api/routes/v1/history.py`
- 已完成边界：历史列表、单会话详情、练后 review 读取契约、review 持久化快照
- 已完成边界：前端 `HistoryPage` 与 `PostPracticeReviewPage` 已切到真实后端读取
- 仍然缺失：真实用户鉴权范围、分页/筛选、 richer review 生成策略

## 输入输出契约

- 输入：用户标识、会话标识、筛选条件
- 输出：历史会话列表、单会话详情、复盘信息
- 关键字段：`session_id`、`messages`、场景、角色、反馈

## 代码位置

- `api/models/session_model.py`
- `api/models/message_model.py`
- `api/db/session_db.py`

## 当前工作

- `[x]` 明确历史查询输出结构
- `[x]` 设计最小回放接口
- `[x]` 补会话读取与排序测试
- `[ ]` 引入真实用户范围与分页

## 测试门

- `module_test_passed` 的标准：历史列表、详情和 review 读取稳定可验证
- 最少要覆盖的用例：空历史、单会话详情、多会话排序、review 快照读取
- 还没覆盖的风险：后续真实鉴权接入后的用户隔离、分页和字段扩展

## 阻塞项

- 当前仍使用 `default_user_id`，未进入真实鉴权流
- 还没有分页、筛选和 richer review 生成策略

## 变更记录

- `2026-03-30`：初始化模块状态文档
- `2026-04-04`：新增 history 列表/详情与 session review 真实接口，前端 history/review 页面切真
