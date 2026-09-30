# Bug: `auth-form-empty-field-validation`

## 基本信息

- `bug`: `auth-form-empty-field-validation`
- `status`: `feature_test_passed`
- `branch`: `feature/frontend_app/login-success-notice`
- `owner`: `codex`
- `reported_at`: `2026-04-05`
- `affected_area`: `frontend_app`

## 现象

登录页和注册页曾出现两类英文错误直出：
- 邮箱或密码为空时显示 `"Validation error"`。
- 登录凭证错误时显示 `"Invalid email or password"`。

## 复现步骤

1. 打开 `/login` 或 `/register` 页面。
2. 将邮箱或密码保留为空，或只输入空格后直接提交。
3. 页面发起真实 auth 请求，并在错误区域显示后端返回的英文错误文案。

## 预期结果

- 登录页空邮箱时显示 `邮箱不能为空`。
- 登录页空密码时显示 `密码不能为空`。
- 登录页邮箱或密码错误时显示 `邮箱/密码错误`。
- 注册页空昵称/邮箱/密码时分别显示对应的中文“不能为空”提示。
- 前端在空值场景下不应继续向后端发请求。

## 实际结果

- 空值输入仍然触发 `auth.login()` / `auth.register()`。
- 后端 `RequestValidationError` 被统一包装成 `"Validation error"`，前端只读取顶层 `message` 后直接展示。
- 登录凭证错误时，后端返回 `"Invalid email or password"`，前端同样直接透传英文原文。

## 影响范围

- 用户影响：首次注册或登录时会看到英文错误，且无法快速判断是空值问题还是凭证错误。
- 模块影响：`frontend_app` 的 auth 表单体验与中文化目标不一致，前端既没有完全拦住空值输入，也没有对后端凭证错误做本地化映射。
- 数据影响：无持久化脏数据，但会产生不必要的 400 请求。

## 根因

`frontend/src/pages/LoginPage.tsx` 和 `frontend/src/pages/RegisterPage.tsx` 在第一阶段没有做完整的登录表单本地化错误收口：
- 空值场景下，页面未先拦截输入，导致后端 `api/main.py` 把请求校验失败统一返回 `message="Validation error"`。
- 凭证错误场景下，`frontend/src/services/authApi.ts` 直接透传后端 `"Invalid email or password"`，没有在 service 层做中文映射。

两类错误最终都在页面上以英文文案直出。

## 修复方案

- 改了什么：
  - 在登录页提交逻辑里增加 `trim()` 后的邮箱/密码非空校验，并在失败时直接展示中文文案。
  - 在注册页提交逻辑里增加 `trim()` 后的昵称/邮箱/密码非空校验，并在失败时阻止请求发出。
  - 在 `frontend/src/App.test.tsx` 增加注册/登录空值回归测试，断言中文提示出现且 `authApi` 未被调用。
  - 在 `frontend/src/services/authApi.ts` 增加登录失败文案映射，把 `"Invalid email or password"` 统一翻译成 `邮箱/密码错误`。
  - 在 `frontend/src/services/authApi.test.ts` 和 `frontend/src/App.test.tsx` 增加登录凭证错误回归测试。
- 为什么这样改：
  - 空值问题属于前端入口校验缺失，应在页面层拦截。
  - 凭证错误问题属于前端 service 层本地化缺失，应在 `authApi` 统一映射，避免页面层重复判断。
- 是否有兼容性风险：
  - 风险低；不改后端契约，不改成功路径，只在前端补本地校验和错误翻译。

## 验证

- 测试命令：
  - `npm test -- --run src/App.test.tsx src/services/authApi.test.ts`
  - `uv run pytest tests/api/test_auth_routes.py -q`
- 验证结果：
  - 前端测试通过，`2 passed / 28 passed`，新增空值和登录凭证错误回归用例全部通过。
  - 后端 auth 路由测试通过，`13 passed in 2.70s`，说明前端修复未影响既有 auth API 契约。
- 仍需关注：
  - 找回密码和重置密码页面当前未纳入本轮统一校验范围，后续若需要一致体验，可按相同方式补齐。

## 关闭条件

- 从 `in_progress` 到 `feature_test_passed`：登录/注册空值回归测试通过，且页面不再展示英文 `"Validation error"` 或 `"Invalid email or password"`。
- 从 `feature_test_passed` 到 `merged_to_module`：代码和缺陷文档合入前端模块分支。
- 从 `merged_to_module` 到 `closed`：后续认证页面统一策略确认完成，且同类空值提示问题不再复发。
