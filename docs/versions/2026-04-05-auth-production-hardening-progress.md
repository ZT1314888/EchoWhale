# Version: `2026-04-05-auth-production-hardening-progress`

## 基本信息

- `version`: `2026-04-05-auth-production-hardening-progress`
- `status`: `integrating`
- `branch`: `bugfix/auth/register-parent-flush-order`
- `created_at`: `2026-04-05`
- `published_at`: ``

## 版本摘要

这一版把 EchoWhale 的 `auth` 从“可跑通的 v1 登录链路”收口到了“生产核心闭环”。重点完成了三件事：前端运行时自动续期与统一 401 恢复、后端生产配置/输入/并发语义硬化，以及邮箱验证 + 密码找回闭环。当前 `auth` 已不再停留在基础登录 demo，而是具备了待验证注册、限流、一次性验证/重置 token 和密码重置后旧会话撤销等生产必需语义。

## 包含内容

- `api/`
  - 更新 `api/routes/v1/auth.py`
  - 更新 `api/services/auth_service.py`
  - 更新 `api/db/auth_db.py`
  - 更新 `api/core/config.py`
  - 更新 `api/core/security.py`
  - 更新 `api/main.py`
  - 新增 `api/models/auth_token_model.py`
  - 新增 `api/services/auth_mailer.py`
  - 新增 `api/services/auth_rate_limit.py`
  - 新增迁移 `api/migrations/versions/20260405_0006_add_auth_action_tokens.py`
- `frontend/`
  - 更新 `frontend/src/auth/AuthProvider.tsx`
  - 更新 `frontend/src/App.tsx`
  - 更新 `frontend/src/pages/LoginPage.tsx`
  - 更新 `frontend/src/pages/RegisterPage.tsx`
  - 更新 `frontend/src/services/apiClient.ts`
  - 更新 `frontend/src/services/authApi.ts`
  - 更新 `frontend/src/types/app.ts`
  - 新增 `frontend/src/pages/VerifyEmailPage.tsx`
  - 新增 `frontend/src/pages/ForgotPasswordPage.tsx`
  - 新增 `frontend/src/pages/ResetPasswordPage.tsx`
- `tests/`
  - 更新 `tests/core/test_config.py`
  - 更新 `tests/api/test_auth_routes.py`
  - 更新 `tests/services/test_auth_service.py`
  - 更新 `tests/db/test_auth_repository_fk_order.py`
  - 更新 `frontend/src/auth/AuthProvider.test.tsx`
  - 更新 `frontend/src/services/apiClient.test.ts`
  - 更新 `frontend/src/services/authApi.test.ts`
  - 更新 `frontend/src/App.test.tsx`
- `docs/`
  - 更新 `docs/modules/auth/status.md`
  - 更新 `docs/control/project-index.md`
  - 新增 `docs/versions/2026-04-05-auth-production-hardening-progress.md`

## 完成情况

- 已完成：
  - 前端 access token 运行时自动续期，并在 401 后共享一次 `refresh` 再重放原请求
  - 生产环境 auth 配置硬门禁：默认 secret、不安全 cookie、空 `allowed_origins` 不再允许启动
  - 登录/注册输入校验收紧，`users.status` 对 `login / refresh / me` 生效
  - 注册并发冲突收口为稳定业务错误
  - refresh token 改为数据库层原子轮换，单个 token 只能消费一次
  - 新增 auth 限流
  - 新增邮箱验证、重发验证、忘记密码和重置密码闭环
  - 密码重置后撤销旧 refresh 会话
- 未完成但已明确留到下一阶段：
  - OAuth 登录
  - 匿名 visitor 数据绑定到正式账号
  - 设备会话管理与更完整审计日志

## 验证结果

- backend：
  - 执行 `uv run pytest tests/core/test_config.py tests/api/test_auth_routes.py tests/services/test_auth_service.py tests/db/test_auth_repository_fk_order.py -q`
  - 结果：`28 passed in 6.01s`
- frontend：
  - 执行 `npm test`
  - 结果：`10 files passed, 37 tests passed`
  - 执行 `npm run build`
  - 结果：构建通过，产物写入 `frontend/dist/`

## 后续工作

- 用真实 PostgreSQL + HTTPS cookie 跑一次系统级认证态联调
- 选定真实邮件供应商并替换 `AuthMailer` adapter
- 进入 Phase 2：OAuth、设备会话、审计日志和匿名数据绑定策略
