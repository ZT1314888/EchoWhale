# Feature: `frontend_quality_gates`

## 基本信息

- `feature`: `frontend_quality_gates`
- `status`: `feature_test_passed`
- `module`: `frontend_app`
- `cross_module`: `yes`（新增仓库级 CI，覆盖 backend pytest）
- `owner`: `lucky`
- `updated_at`: `2026-09-30`
- `merge_target`: `module/frontend_app`

## 背景

前端类型检查自项目起步起就不是门禁：`tsc --noEmit` 长期带着 14 个与业务无关的基线错误，`tsconfig` 的 lib 还停在 ES2020（代码却用了 `.at()`）；SSE 读取器在中途失败/取消时从不释放；所有测试与类型检查都靠人肉执行，仓库没有任何 CI。

## 用户故事

- 当我提交一个前端改动，我希望 `tsc` 与 vitest 在 CI 上自动跑一遍，类型回归在合并前就被拦下。
- 当文字回合在中途被取消或断流，我希望底层读取器被释放，而不是留下悬挂的锁。

## 范围

### In scope

- `tsconfig.json`：target/lib 升至 ES2022（消除 5 处 `.at()` 误报），新增 `frontend/src/vite-env.d.ts`（vite/client 资源模块声明，消除 3 处静态图片导入报错）
- `apiClient.ts`：请求对象字面量 `credentials: "include" as const`（消除展开宽化）
- `sessionApi.ts`：`submitPracticeTurnStream` 的回调赋值改 holder 对象 + `const` 提取判空（消除 3 处 `never` 收窄误报）；`consumeSseResponse` 循环包进 `try/finally`，退出时 `reader.cancel().catch()` 收回读取器（取消/断流不再泄漏锁与流）
- `practiceApi.ts`：示例场景白名单 `SAMPLE_SCENE_IDS as const` + `isSampleSceneId` 类型守卫（消除字面量联合收窄报错）
- `package.json` 新增 `typecheck` 脚本；新增 `.github/workflows/ci.yml`：backend（uv sync --frozen → pytest）+ frontend（npm ci → typecheck → vitest）双 job，带 concurrency 取消与 npm/uv 缓存
- 测试：`sessionApi.test.ts` 新增「中途失败 → 原始错误透传 + reader.cancel 被调用」用例（spy 在 `ReadableStreamDefaultReader.prototype.cancel`）

### Out of scope

- vitest 覆盖率阈值配置
- lint/ruff/black 接入 CI
- AudioWorklet 迁移等语音主链路改动

## 设计要点

- 回调闭包内的赋值不被 TS 控制流分析跟踪：`let x: T | null = null` 在回调后会被收窄成 `null`，改用属性 holder（属性收窄会被中间调用重置）+ `const` 提取后判空，是最小改动方案
- `reader.cancel()` 对已 errored 的流自身会拒绝（且不再触发底层 cancel），必须 `.catch()` 静默；观察手段是 spy 公开方法而非断言底层 source.cancel
- CI 双 job 并行：后端用 `uv sync --frozen`（lockfile 校验通过）+ 无 .env 环境（默认 mock 模式，天然满足测试前提）；前端 `npm ci` 走 lockfile

## 测试

- `npx tsc --noEmit`：0 error（本批前 13 error）
- `npx vitest run`：99 passed（基线 98 + 新增 1）
- `uv run pytest tests`：224 passed / 2 skipped（零回归）
- `.github/workflows/ci.yml` 经 YAML 解析校验结构
- CI 配方已本地全真模拟：仅注入 `DATABASE_URL=sqlite+aiosqlite:///./ci.db`（无 .env）+ 预建表步骤 → pytest 224 passed / 2 skipped，与 workflow 步骤逐字一致
