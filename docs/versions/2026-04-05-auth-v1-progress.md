# Version: `2026-04-05-auth-v1-progress`

## 基本信息

- `version`: `2026-04-05-auth-v1-progress`
- `status`: `integrating`
- `branch`: `feature/media_upload/r2-pipeline`
- `created_at`: `2026-04-05`
- `published_at`: ``

## 版本摘要

今天完成了 EchoWhale `auth` v1 的第一次真实落地：后端新增邮箱密码认证、refresh cookie 和 visitor 身份，前端新增真实登录态恢复与 `/history` 守卫，原先依赖 `default_user_id` 的 `media/session/history` 主链路已切到 `user:* / visitor:*` owner 命名空间。当前交付已把系统从“demo 用户占位”推进到“真实账号 + 匿名试玩并存”的可验证阶段。

## 包含内容

- `api/`
  - 新增 `api/routes/v1/auth.py`
  - 新增 `api/services/auth_service.py`
  - 新增 `api/db/auth_db.py`
  - 新增 `api/core/security.py`
  - 新增 `api/common/ownership.py`
  - 新增 `api/models/auth_model.py`
  - 更新 `api/common/deps.py`
  - 更新 `api/routes/v1/media.py`
  - 更新 `api/routes/v1/sessions.py`
  - 更新 `api/routes/v1/history.py`
  - 更新 `api/services/media_service.py`
  - 更新 `api/modules/session_engine/service.py`
  - 更新 `api/db/database.py`
  - 更新 `api/migrations/env.py`
  - 新增迁移 `api/migrations/versions/20260405_0005_create_auth_tables.py`
- `frontend/`
  - 新增 `frontend/src/auth/AuthProvider.tsx`
  - 新增 `frontend/src/auth/RequireAuth.tsx`
  - 新增 `frontend/src/services/apiClient.ts`
  - 新增 `frontend/src/services/authApi.ts`
  - 更新 `frontend/src/App.tsx`
  - 更新 `frontend/src/pages/LoginPage.tsx`
  - 更新 `frontend/src/pages/RegisterPage.tsx`
  - 更新 `frontend/src/services/mediaApi.ts`
  - 更新 `frontend/src/services/sessionApi.ts`
  - 更新 `frontend/src/services/reviewApi.ts`
  - 更新 `frontend/src/services/historyApi.ts`
  - 更新 `frontend/src/types/app.ts`
- `tests/`
  - 新增 `tests/api/test_auth_routes.py`
  - 新增 `tests/services/test_auth_service.py`
  - 更新 `tests/api/test_media_routes.py`
  - 更新 `tests/api/test_session_routes.py`
  - 更新 `tests/modules/test_session_engine.py`
  - 新增 `frontend/src/services/authApi.test.ts`
  - 更新 `frontend/src/App.test.tsx`
- `docs/`
  - 新增 `docs/modules/auth/status.md`
  - 更新 `docs/control/project-index.md`
  - 更新 `docs/modules/session_orchestration/status.md`
  - 更新 `docs/modules/history_review/status.md`
  - 更新 `docs/modules/frontend_app/status.md`

## 完成情况

- 已完成：
  - 新增真实认证路由：`register/login/refresh/me/logout`
  - 新增 `users / user_credentials / refresh_tokens` 持久化模型与迁移
  - access token 改为 JWT，refresh token 改为 HttpOnly Cookie 持久化
  - `media/session/review` 匿名链路改为 `visitor_id` 驱动，不再依赖 `default_user_id`
  - `history` 改为必须登录，且只返回当前真实用户的资源
  - 前端登录/注册页切到真实 auth API，应用启动会尝试 refresh 恢复登录态
  - `/history` 已增加前端登录守卫，匿名访问会跳转到 `/login?next=...`
- 未完成但可接受：
  - 匿名 visitor 数据仍不会自动并入正式账号历史
  - OAuth、邮箱验证、密码找回仍未纳入本版
- 已知限制：
  - 当前仍缺少一次携带真实 R2 结果的系统级认证态联调
  - 正式环境 `cookie secure`、密钥轮换和匿名升级绑定策略仍需进一步收口

## 验证结果

- backend：
  - 执行 `uv run pytest tests/core/test_config.py tests/db/test_media_repository.py tests/db/test_session_repository.py tests/db/test_session_repository_fk_order.py tests/api/test_media_routes.py tests/api/test_session_routes.py tests/api/test_auth_routes.py tests/modules/test_session_engine.py tests/services/test_auth_service.py -q`
  - 结果：`38 passed in 5.17s`
- frontend：
  - 执行 `npm test`
  - 结果：`8 files passed, 23 tests passed`
  - 执行 `npm run build`
  - 结果：构建通过，产物写入 `frontend/dist/`
- system：
  - 本版目标是 auth v1 与匿名 visitor 主链路落地，不在本轮内宣称 full flow 发布验证通过

## 发布说明

- 发布前检查：
  - 当前不是正式发布版本，而是 auth v1 落地后的阶段性进度快照
- 发布方式：
  - 暂不发布
- 回滚方式：
  - 若需回退，可聚焦 `api/routes/v1/auth.py`、`api/services/auth_service.py`、`api/common/deps.py`、`frontend/src/auth/` 与相关 API 接线改动

## 后续工作

- 下一版要补什么：
  - 补一次带真实 R2 结果的 `upload -> session -> review -> history` 认证态联调
  - 决定匿名 visitor 数据是否需要升级绑定到正式账号
  - 评估 OAuth、邮箱验证、密码找回的落地顺序
- 哪些 feature 仍在 `planned` 或 `in_progress`：
  - `media_upload` 仍缺少真实 R2 联调闭环
  - `session_orchestration` 仍缺少更完整系统联调与 voice 分支
  - `auth` 仍有账号体系扩展项未纳入本版
