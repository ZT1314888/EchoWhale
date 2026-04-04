# Bug: `session-save-parent-flush-order`

## 基本信息

- `bug`: `session-save-parent-flush-order`
- `status`: `feature_test_passed`
- `branch`: `feature/frontend_app/frontend-worktree-snapshot-20260404`
- `owner`: `codex`
- `reported_at`: `2026-04-04`
- `affected_area`: `session_orchestration`

## 现象

`POST /api/v1/sessions` 在 PostgreSQL 下创建首轮 assistant opener 时返回 500，并抛出 `session_messages_session_id_fkey` 外键错误。

## 复现步骤

1. 准备一个 `upload_status=uploaded` 的 media。
2. 调用 `POST /api/v1/sessions` 创建新 session。
3. 后端进入 `SqlAlchemySessionRepository.save_session()`，尝试同时保存父 session 和首条 assistant message。

## 预期结果

- 新 session 与首条 assistant opener 一起成功持久化。
- 接口返回 200，并包含 `session_id` 和 opener message。

## 实际结果

- `session_messages` 先于 `sessions` 执行插入。
- PostgreSQL 立即校验外键并拒绝写入，接口返回 500。

## 影响范围

- 用户影响：上传成功后无法进入真实练习会话。
- 模块影响：`session_orchestration` 的 `start_session` 主链路中断。
- 数据影响：事务会回滚，不会留下半成品 session，但主流程不可用。

## 根因

`api/db/session_db.py` 中的 `save_session()` 只 `add(SessionRecord)`，没有在写 `MessageRecord` 前先 `flush()` 父记录。`SessionRecord` 和 `MessageRecord` 之间没有 ORM `relationship` 建立 flush 依赖，而 session factory 又配置了 `autoflush=False`，导致首次 flush 时可能先发子表 insert，在 FK 严格数据库下立刻失败。

## 修复方案

- 改了什么：
  - 在 `save_session()` 里 `_upsert_session_record(...)` 之后显式 `db_session.flush()`。
  - 新增强 FK 回归测试 `tests/db/test_session_repository_fk_order.py`。
- 为什么这样改：
  - 用最小改动确保父 `sessions` 先落库，再执行 message 删除与重建。
- 是否有兼容性风险：
  - 风险低；只改变同一事务中的 flush 时机，不改变接口契约或 schema。

## 验证

- 测试命令：
  - `.\.venv\Scripts\python.exe -m pytest tests\db\test_session_repository_fk_order.py -q`
  - 一次性 PostgreSQL 验证脚本：直接调用 `SqlAlchemySessionRepository.save_session()` 保存带 opener 的 session，再清理验证数据。
- 验证结果：
  - 新回归测试先红后绿，最终 `1 passed`。
  - PostgreSQL 实际仓储路径验证输出：`PG_SAVE_OK ... 1 ...`。
- 仍需关注：
  - 现有 `tests/db/test_session_repository.py` 仍以 SQLite + `tmp_path` 为主，且当前 Windows 环境存在 pytest 临时目录权限噪音，需要后续单独收口测试基建。

## 关闭条件

- 从 `in_progress` 到 `feature_test_passed`：强 FK 回归测试通过，且 PostgreSQL 实际路径验证成功。
- 从 `feature_test_passed` 到 `merged_to_module`：代码与文档合入对应模块分支。
- 从 `merged_to_module` 到 `closed`：系统联调中 `upload -> session` 主链路稳定，不再出现同类 FK 顺序问题。
