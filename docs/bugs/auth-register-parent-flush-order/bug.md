# Bug: `auth-register-parent-flush-order`

## 基本信息

- `bug`: `auth-register-parent-flush-order`
- `status`: `feature_test_passed`
- `branch`: `bugfix/auth/register-parent-flush-order`
- `owner`: `codex`
- `reported_at`: `2026-04-05`
- `affected_area`: `auth`

## 现象

`POST /api/v1/auth/register` 在 PostgreSQL 下注册账号时返回 500，并抛出 `user_credentials_user_id_fkey` 外键错误。

## 复现步骤

1. 启动带 auth migration 的 EchoWhale 后端并连接 PostgreSQL。
2. 调用 `POST /api/v1/auth/register`，提交合法的 `nickname/email/password`。
3. 后端进入 `SqlAlchemyAuthRepository.create_user()`，尝试在同一事务里保存 `users` 和 `user_credentials`。

## 预期结果

- 新用户与 password credentials 一起成功持久化。
- 接口返回 200，并返回 access token、refresh cookie 和用户摘要。

## 实际结果

- `user_credentials` 先于 `users` 执行插入。
- PostgreSQL 立即校验外键并拒绝写入，接口返回 500。

## 影响范围

- 用户影响：注册账号主链路不可用，前端注册页无法完成首登。
- 模块影响：`auth` 的 `register` 路径中断，后续 `refresh/login/me` 无法建立在新账号上验证。
- 数据影响：事务会回滚，不会留下半成品 credentials，但用户无法创建账号。

## 根因

`api/db/auth_db.py` 中的 `create_user()` 只 `add(UserRecord)` 后立即继续 `add(UserCredentialRecord)`，没有像 `session_db.save_session()` 一样在写子记录前显式 `flush()` 父记录。`UserRecord` 和 `UserCredentialRecord` 之间没有 ORM `relationship` 来建立 flush 依赖，且 session factory 配置了 `autoflush=False`，导致首次 flush 可能先发 `user_credentials` insert，在 FK 严格数据库下立刻失败。

## 修复方案

- 改了什么：
  - 在 `SqlAlchemyAuthRepository.create_user()` 里新增一次 `session.flush()`，强制先落父 `users` 记录，再写 `user_credentials`。
  - 为 `tests/services/test_auth_service.py` 的 SQLite helper 打开 `PRAGMA foreign_keys=ON`。
  - 新增强 FK 回归测试 `tests/db/test_auth_repository_fk_order.py`。
- 为什么这样改：
  - 用最小改动修正事务内的父子写入顺序，并让现有 auth 测试环境和生产 FK 语义对齐。
- 是否有兼容性风险：
  - 风险低；只改变同一事务中的 flush 时机，不改变表结构、接口契约或 token/cookie 行为。

## 验证

- 测试命令：
  - `uv run pytest tests/db/test_auth_repository_fk_order.py -q`
  - `uv run pytest tests/services/test_auth_service.py -q`
- 验证结果：
  - 新回归测试修复前 `1 failed`，修复后 `1 passed in 0.53s`。
  - auth service 严格 FK 测试修复前 `3 failed`，修复后 `3 passed in 1.73s`。
- 仍需关注：
  - 线上 PostgreSQL 环境还需要再跑一次真实 `POST /api/v1/auth/register`，确认接口级 500 已消失。

## 关闭条件

- 从 `in_progress` 到 `feature_test_passed`：严格 FK 回归测试和 auth service 测试全部通过。
- 从 `feature_test_passed` 到 `merged_to_module`：代码与文档合入对应 auth 模块分支。
- 从 `merged_to_module` 到 `closed`：真实 PostgreSQL 注册链路稳定，不再出现同类 FK 顺序错误。
