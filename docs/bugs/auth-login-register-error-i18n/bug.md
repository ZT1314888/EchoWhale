# Bug: `auth-login-register-error-i18n`

## 基本信息

- `bug`: `auth-login-register-error-i18n`
- `status`: `feature_test_passed`
- `branch`: `feature/frontend_app/login-success-notice`
- `owner`: `codex`
- `reported_at`: `2026-04-05`
- `affected_area`: `frontend_app`

## 现象

登录页和注册页在非空但参数不合法的场景下，仍会显示后端返回的英文错误提示。

## 复现步骤

1. 打开 `/login` 或 `/register` 页面。
2. 输入非空但不合法的邮箱或密码，例如邮箱格式错误、密码不满足规则，或使用待验证账号登录。
3. 提交表单，观察页面错误提示。

## 预期结果

- 登录页和注册页不再展示 `Validation error`、`Invalid email format`、`Email already registered` 等英文错误。
- 登录页非法邮箱显示 `邮箱格式错误`。
- 登录页和注册页密码规则错误统一显示 `密码至少 8 位且需包含字母和数字`。
- 待验证账号登录显示 `请先完成邮箱验证后再登录`。
- 注册重复邮箱显示 `该邮箱已被注册`。
- 登录/注册限流错误显示对应中文提示。

## 实际结果

- 前端之前只把 `"Invalid email or password"` 映射成中文。
- 后端 `RequestValidationError` 的具体错误被放在 `data[].msg`，前端没有读取，最终把顶层 `"Validation error"` 直接展示给用户。
- 注册重复邮箱、待验证账号登录和登录/注册限流等英文 message 也会直接展示。

## 影响范围

- 用户影响：登录/注册失败时仍会看到英文错误，无法稳定区分格式错误、重复邮箱、待验证状态和限流。
- 模块影响：`frontend_app` 的 auth 错误提示中文化不完整，登录/注册流程体验不一致。
- 数据影响：无持久化数据损坏，仅影响交互反馈质量。

## 根因

`frontend/src/services/authApi.ts` 只依赖后端响应顶层 `message`，没有按 auth 场景解析错误细节：

- 对 `RequestValidationError`，后端 `api/main.py` 统一返回 `message="Validation error"`，真实字段级原因在 `data[].msg`。
- 对 `Email already registered`、`Please verify your email before logging in`、登录/注册 rate limit 等后端已知英文 message，前端缺少统一翻译映射。
- 页面层已经处理了空值拦截，但 service 层没有把“非空但不合法”的后端错误收口成中文。

## 修复方案

- 改了什么：
  - 在 `frontend/src/services/authApi.ts` 增加 auth 错误翻译层，统一解析顶层 message 和 `Validation error` 的 `data[].msg`。
  - 为登录/注册增加 endpoint-aware 中文兜底，避免未来新增校验规则时再次直出英文 `Validation error`。
  - 在 `frontend/src/services/authApi.test.ts` 增加非法邮箱、密码规则、待验证账号、重复邮箱、限流和未知校验细节的回归测试。
  - 在 `frontend/src/App.test.tsx` 增加登录/注册页展示中文错误的页面级回归测试，并断言对应英文原文不再出现。
- 为什么这样改：
  - auth 错误翻译属于 service 层横切逻辑，放在 `authApi` 能避免各页面重复判断。
  - 保持后端契约不变，可以最小范围修复当前用户可见问题。
- 是否有兼容性风险：
  - 风险低；不改后端接口、不改成功路径，只增强前端错误解析和测试覆盖。

## 验证

- 测试命令：
  - `npm test -- --run src/App.test.tsx src/services/authApi.test.ts`
  - `uv run pytest tests/api/test_auth_routes.py -q`
- 验证结果：
  - 前端 auth 相关测试通过，`39 passed`，新增登录/注册中文错误回归全部通过。
  - 后端 auth 路由测试通过，`13 passed in 2.37s`，说明前端翻译层未影响既有 auth 契约。
- 仍需关注：
  - 本轮只覆盖登录/注册提交后的错误提示，不处理登录/注册页静态英文文案。
  - 认证链路其他页面如验证邮箱、找回密码、重置密码若后续要求统一中文化，可沿用相同模式继续收口。

## 关闭条件

- 从 `in_progress` 到 `feature_test_passed`：登录/注册相关前端回归测试通过，页面不再展示本轮已覆盖的英文错误。
- 从 `feature_test_passed` 到 `merged_to_module`：代码和 bug 文档合入前端模块分支。
- 从 `merged_to_module` 到 `closed`：认证流程错误提示中文化策略稳定，登录/注册同类英文残留不再复发。
