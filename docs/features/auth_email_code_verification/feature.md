# Feature: `auth_email_code_verification`

## 基本信息

- `feature`: `auth_email_code_verification`
- `module`: `auth`
- `status`: `feature_test_passed`
- `updated_at`: `2026-04-08`

## 目标

把原来的邮箱链接激活改成 6 位邮箱验证码激活，并接入 Redis 频控与基于 RQ + Redis 的认证邮件异步发送能力。

## 当前实现

- `POST /api/v1/auth/register`
  - 创建 `pending_verification` 用户
  - 生成 6 位验证码
  - 发布验证码邮件任务到 `auth-mail` 队列
- `POST /api/v1/auth/resend-verification`
  - 对 `pending_verification` 用户重发验证码
  - 新验证码覆盖旧验证码
  - 成功入队后立即返回，不等待 SMTP 完成
- `POST /api/v1/auth/verify-email`
  - 请求体改为 `email + code`
  - 验证成功后激活用户
- `POST /api/v1/auth/forgot-password`
  - 生成一次性重置链接
  - 发布密码重置邮件任务到 `auth-mail` 队列

## 队列边界

- `AuthService` 只负责生成验证码 / reset token 并发布任务，不再直接调用 SMTP
- worker 任务位于 `api/tasks/auth_mail_tasks.py`
- 实际 SMTP 发送仍由 `SmtpAuthMailer` 执行
- HTTP 侧只要成功入队就维持现有成功响应
- Redis / RQ 入队失败会返回受控 `503`
- SMTP 真正发送失败会留给 worker 重试与日志处理，不再阻塞当前请求

## Redis 规则

- 同一邮箱 60 秒内最多发送 1 次
- 同一 IP 60 秒内最多发送 1 次
- 同一邮箱每天最多发送 5 次
- 同一 IP 每天最多发送 5 次
- 验证码默认有效期 10 分钟
- 验证成功后验证码立即删除

## 代码位置

- `api/services/email_verification_store.py`
- `api/services/auth_service.py`
- `api/services/auth_mail_queue.py`
- `api/services/auth_mailer.py`
- `api/tasks/auth_mail_tasks.py`
- `api/tasks/worker.py`
- `api/routes/v1/auth.py`
- `frontend/src/pages/VerifyEmailPage.tsx`

## 验证

- backend
  - `uv run pytest tests/core/test_config.py tests/services/test_auth_mailer.py tests/api/test_auth_routes.py -q`
  - `uv run pytest tests/services/test_email_verification_store.py tests/services/test_auth_service.py tests/api/test_auth_routes.py -q`
  - `uv run pytest tests/services/test_auth_service.py tests/services/test_auth_mail_queue.py tests/api/test_auth_routes.py -q`
- frontend
  - `npm test -- --run src/services/authApi.test.ts src/App.test.tsx`

## 2026-04-07 Bugfix

- `resend-verification` 真实联调时暴露出 SMTP 认证失败会直接冒泡成原始 `500 Internal Server Error`
- 当前已补两层防护：
  - 启动期校验 SMTP 配置完整性，禁止 `SSL + STARTTLS` 同时开启
  - 发送期将 `SMTPAuthenticationError` / 传输异常统一翻译为受控应用异常，避免把底层 `smtplib` traceback 直接暴露给前端

## 已知风险

- 真实 Redis / SMTP 联通仍需在目标环境做一次 smoke
- worker 进程需要和 API 进程分开启动，否则队列中的认证邮件不会真正消费
- `forgot-password/reset-password` 当前改为邮件重置链接，服务端内部仍使用一次性 token 作为链接凭据，暂未统一成验证码流
