# Feature: `login_success_notice`

## 基本信息

- `feature`: `login_success_notice`
- `status`: `feature_test_passed`
- `branch`: `feature/frontend_app/login-success-notice`
- `module`: `frontend_app`
- `cross_module`: `no`
- `owner`: `codex`
- `updated_at`: `2026-04-05`

## 背景

用户登录成功后会直接跳回首页，但页面缺少成功反馈，导致动作已经完成却没有明显确认感。需要在不打断后续操作的前提下，给出一次性、轻量的登录成功提示。

## 用户故事

- 当我完成登录
- 我希望首页马上给我一个清晰的成功提示
- 这样我就能确认自己已经成功进入系统，而不是怀疑登录是否生效

## 范围

### In scope

- 登录成功后在首页显示一次性提示
- 提示文案使用简体中文
- 提示支持自动消失和手动关闭
- 提示只在本次登录跳转后出现一次，不在刷新或再次进入首页时重复出现

### Out of scope

- 后端 auth 契约修改
- 全局 toast 系统建设
- 注册成功、登出成功等其他提示统一收口

## 设计要点

- 关键流程：登录页在成功后通过路由 state 带上 `loginSuccess` 标记，首页读取后展示提示并立刻清空该 state
- 依赖模块：`frontend_app`
- 关键数据：一次性路由状态 `loginSuccess: true`
- 失败时如何处理：若首页未读到该 state，则不展示提示，页面保持原有行为

## 验收标准

- `[x]` 登录成功后跳转到首页时，首页显示中文成功提示
- `[x]` 提示支持用户手动关闭，并在短时间后自动消失
- `[x]` 普通直接访问首页时，不会误显示该提示

## 测试记录

- `feature_test_passed` 的证据：`frontend/src/App.test.tsx` 中登录成功回首页用例通过
- 主要测试命令：`npm test -- --run src/App.test.tsx`，`npm run build`
- 已知缺口：当前提示仍为页面级局部实现，尚未抽象为全局通知系统

## 合并与关闭

- 何时可以写成 `merged_to_module`
  该提示与前端主路径一起合入 `module/frontend_app` 后
- 何时可以写成 `closed`
  模块级验证完成，且后续不再需要对登录成功提示做额外收口时
- 相关文档链接：
  - `frontend/src/pages/LoginPage.tsx`
  - `frontend/src/pages/HomeUploadPage.tsx`
  - `frontend/src/styles/flash-toast.css`
