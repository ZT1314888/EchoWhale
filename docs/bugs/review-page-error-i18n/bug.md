# Bug: `review-page-error-i18n`

## 基本信息

- `bug`: `review-page-error-i18n`
- `status`: `feature_test_passed`
- `branch`: `feature/frontend_app/login-success-notice`
- `owner`: `codex`
- `reported_at`: `2026-04-05`
- `affected_area`: `frontend_app`

## 现象

练后反馈页在 review 缺失或尚未生成时，标题下方会直接展示后端英文错误，例如 `Session review sess_552fc05a3fac not found`。

## 复现步骤

1. 打开真实练习会话的练后反馈页，例如 `/session/sess_552fc05a3fac/review`。
2. 让后端返回 review 缺失的 404 响应。
3. 观察失败态标题下方的提示文案。

## 预期结果

- 页面保留中文失败态标题 `练后反馈还没准备好`。
- 页面不再展示任何英文或技术性错误细节。
- 用户仍可通过按钮返回练习页继续操作。

## 实际结果

- `frontend/src/services/reviewApi.ts` 之前直接透传后端 `payload.message`。
- `frontend/src/pages/PostPracticeReviewPage.tsx` 又把该 message 作为副文案展示。
- 导致后端英文 `Session review ... not found` 直接暴露在页面上。

## 影响范围

- 用户影响：练后反馈失败态出现英文和技术细节，破坏中文体验，也容易让用户误以为系统异常。
- 模块影响：`frontend_app` 的 review 页面错误收口不完整，与登录/注册页已做的中文错误映射不一致。
- 数据影响：无持久化数据损坏，仅影响页面展示与错误反馈质量。

## 根因

- `reviewApi` 缺少 review 场景的错误翻译层，对 404/未生成类错误直接使用后端英文 `message`。
- `PostPracticeReviewPage` 在失败态渲染了该 message，导致 service 层未收口的问题被直接暴露到 UI。

## 修复方案

- 改了什么：
  - 在 `frontend/src/services/reviewApi.ts` 增加 review 错误翻译逻辑，将 `Session review ... not found` 和 `Resource not found` 收口为中文 `练后反馈还没准备好。`
  - 在 `frontend/src/pages/PostPracticeReviewPage.tsx` 删除失败态副文案，仅保留标题和返回练习按钮。
  - 在 `frontend/src/services/reviewApi.test.ts` 增加 review 缺失错误的中文回归测试。
  - 在 `frontend/src/App.test.tsx` 增加页面级回归测试，断言英文错误和副文案都不再出现。
- 为什么这样改：
  - 这是前端展示层的局部缺陷，收口在 service + page 两层即可消除英文泄漏，同时不改后端契约。
  - 页面保留现有标题语气，满足当前产品表现要求，避免过度扩展为全局错误体系重构。
- 是否有兼容性风险：
  - 风险低；成功路径、后端接口和 review 数据结构都未改动，只调整失败态文案与展示。

## 验证

- 测试命令：
  - `npm test -- --run src/services/reviewApi.test.ts src/App.test.tsx`
- 验证结果：
  - 前端定向测试通过，`2` 个测试文件共 `29 passed`。
  - 新增 service 级和页面级回归测试都已通过，确认练后反馈页不再展示 `Session review ... not found`。
- 仍需关注：
  - 本轮只修复练后反馈页的英文错误泄漏，不扩展处理其他页面或接口的英文错误映射。

## 关闭条件

- 从 `in_progress` 到 `feature_test_passed`：review 页失败态不再展示英文错误，且前端定向回归测试通过。
- 从 `feature_test_passed` 到 `merged_to_module`：代码与 bug 文档合入前端模块分支。
- 从 `merged_to_module` 到 `closed`：review 失败态展示策略稳定，不再回归为透传后端英文 message。
