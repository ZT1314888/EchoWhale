# Module Status: `auth`

## 基本信息

- `module`: `auth`
- `status`: `module_test_passed`
- `branch`: `module/auth`
- `owner`: `codex`
- `updated_at`: `2026-04-08`

## 模块目标

提供 EchoWhale 的真实邮箱密码认证、登录态恢复和用户归属边界，为历史记录和后续语音链路提供身份底座。

## 当前真相

- 现有实现：`api/routes/v1/auth.py`、`api/contracts/auth.py`、`api/services/auth_service.py`、`api/db/auth_db.py`、`frontend/src/auth/`
- 已完成边界：认证 HTTP request/response 契约已从 route 内联 DTO 收敛到 `api/contracts/auth.py`，`api/routes/v1/auth.py` 仅保留 HTTP adapter 与依赖注入
- 已完成边界：`register/login/refresh/me/logout` 路由已落地，其中 `register` 改为创建 `pending_verification` 账号并发送 6 位验证码邮件，`login/refresh` 只对 `active` 用户签发真实 session
- 已完成边界：`logout` 已改为以 refresh cookie 为准撤销 session，不再要求额外 Bearer token
- 已完成边界：前端登录/注册页已切到真实 auth API，`/history` 已增加登录守卫
- 已完成边界：前端 access token 过期后会自动触发一次共享 `refresh` 并重放原请求，不再在 15 分钟后无感掉线
- 已完成边界：`resend-verification/verify-email/forgot-password/reset-password` 路由已落地；注册验证已切到 `email + code` 契约，密码找回已改为邮件重置链接，服务端仍使用一次性 token 作为链接凭据
- 已完成边界：邮箱验证码已接入 Redis 存储、发送冷却与按邮箱/IP 的自然日发送上限控制；auth 邮件发送已切到 `RQ + Redis` 队列，由 worker 异步调用真实 SMTP mailer
- 已完成边界：生产配置硬门禁、输入校验、`users.status` 检查、注册冲突收口、refresh token 原子轮换和 auth 限流已落地
- 已完成边界：登录后头部改为昵称菜单，匿名时才显示 `登录 / 注册`
- 已完成边界：匿名 visitor 身份已接入 `media/session/review` 主链路，匿名体验不再依赖 `default_user_id`
- 已修复回归：`register` 在严格 FK 数据库下因 `user_credentials_user_id_fkey` 失败的问题已通过显式父表 `flush()` 修复
- 仍然缺失：OAuth、匿名数据绑定到正式账号、设备会话管理与更完整审计日志

## 输入输出契约

- 输入：邮箱、密码、refresh cookie、access token、邮箱验证码、密码重置链接 token
- 输出：注册成功后的用户摘要、登录用户摘要、短期 access token、撤销后的 refresh cookie、一次性验证/重置动作结果
- 关键字段：`user_id`、`email`、`nickname`、`access_token`、`status`

## 代码位置

- `api/routes/v1/auth.py`
- `api/contracts/auth.py`
- `api/services/auth_service.py`
- `api/services/auth_mail_queue.py`
- `api/db/auth_db.py`
- `api/tasks/auth_mail_tasks.py`
- `api/tasks/worker.py`
- `frontend/src/auth/`

## 当前工作

- `[x]` 新增 `users / user_credentials / refresh_tokens` 数据表与迁移
- `[x]` 落地 access token + refresh cookie 认证流
- `[x]` 前端接入真实登录、注册、运行时自动续期和登录态恢复
- `[x]` 注册成功后改为跳转验证码页，不再自动建立登录 session
- `[x]` 落地邮箱验证、密码找回和密码重置闭环
- `[x]` 为关键 auth 动作增加最小限流
- `[x]` 收紧生产配置、输入校验、账号状态门禁和 refresh 原子轮换
- `[x]` 登录后头部切为昵称悬浮菜单，并接入退出登录
- `[x]` 为匿名体验引入 `visitor_id`
- `[ ]` 评估匿名数据是否需要升级绑定到正式账号

## 测试门

- `module_test_passed` 的标准：auth 路由、auth service、history 登录门禁和前端登录态恢复稳定可验证
- 已覆盖：后端 auth route、auth service、验证码 store、history 认证门禁、前端 auth API、history 守卫、登录态恢复、邮箱验证和密码重置流程
- 已覆盖：密码重置邮件链接生成、重置页失效链接引导与成功后自动回登录页
- 已覆盖：auth 邮件入队发布器与 worker 任务的定向单测
- 已覆盖：注册 create-only 契约、登录后昵称菜单和退出登录回匿名态
- 已新增：严格 FK 数据库下的 auth repository 回归测试、开启 FK 校验后的 auth service 测试、refresh 单次消费测试与 auth 限流测试
- 还没覆盖的风险：真实 PostgreSQL + HTTPS cookie 端到端联调、匿名升级绑定、真实 Redis/RQ/SMTP 联调

## 阻塞项

- 当前仍未实现 OAuth、设备会话列表和更完整安全事件审计
- 匿名 visitor 数据目前不会自动并入正式账号历史
- auth-mail worker 仍需在部署脚本或运行文档中显式纳入进程清单

## 变更记录

- `2026-04-05`：新增 auth 后端与前端真实闭环，history 改为登录保护，匿名链路切到 visitor 身份
- `2026-04-05`：修复 auth 注册父子写入顺序问题，新增严格 FK 回归测试并补 auth 缺陷文档
- `2026-04-05`：将注册流改为 create-only，前端改为注册后跳登录页，登录态头部收口为昵称菜单 + 退出登录
- `2026-04-05`：修复 logout 误依赖 Bearer token 导致 refresh cookie 未撤销的问题，退出后刷新不再自动登录
- `2026-04-05`：完成 auth 生产化 Phase 1，新增运行时自动续期、邮箱验证、密码找回、限流、生产配置硬门禁和 refresh token 原子轮换
- `2026-04-07`：将注册验证从邮件链接切到 6 位邮箱验证码，新增 Redis 频控/验证码存储与 SMTP 配置入口，前端验证页改为手动输入验证码
- `2026-04-08`：将密码找回邮件改为发送站内重置链接，前端重置页新增失效链接引导与成功后自动跳转登录页
- `2026-04-08`：新增 `api/contracts/` 分层，auth request/response DTO 从 route 抽离，邮箱/昵称/密码规则收口到 `AuthService`
- `2026-04-08`：将 auth 邮件发送从同步 SMTP 改为 `RQ + Redis` 异步队列；`AuthService` 改为发布邮件任务，worker 侧复用 `SmtpAuthMailer`
