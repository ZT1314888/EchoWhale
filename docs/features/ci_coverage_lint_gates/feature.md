# Feature: `ci_coverage_lint_gates`

## 基本信息

- `feature`: `ci_coverage_lint_gates`
- `status`: `feature_test_passed`
- `module`: `platform_foundation`
- `cross_module`: `yes`（后端 lint 门禁 + 前端 coverage 门禁 + CI 工作流）
- `owner`: `lucky`
- `updated_at`: `2026-10-01`
- `merge_target`: `module/platform_foundation`

## 背景

CI 首跑绿了（dev 分支 36821205442，双 job 全过），但两个 job 都只是"测试能过"：没有任何 lint 检查后端代码质量，前端测试不带覆盖率，回归只能靠用例数量肉眼判断。另外首跑暴露了两条非阻塞注记：checkout/setup-node 的 Node 20 运行时已弃用。

## 用户故事

- 当我提交一段带坏味道的后端代码，我希望 CI 的 ruff 步骤在 pytest 之前直接拦下，而不是等测试偶然踩到。
- 当前端覆盖率跌破底线，我希望 CI 变红并给出数字，而不是静默下滑。

## 范围

### In scope

- ruff 接入（dev 依赖 `ruff>=0.16.9` + `[tool.ruff]` 配置）：extend-select `I/B/UP/RUF/SIM/TRY/FURB/DTZ/BLE`；`flake8-bugbear.extend-immutable-calls` 豁免 FastAPI DI 标记（52 处 B008 全部为 `Depends/File/Query` 官方写法，零真实违规）；仓库约定级豁免（`RUF001/002/003` 中文全角标点、`TRY003` 消息式异常、`UP042/046/047` str-Enum 与旧式 Generic 遗留模式）并逐条写明理由
- 违规清零：154 处自动修复（import 排序、`datetime.UTC` 等）+ 8 处逐个裁决（3 处修复：SIM103 直接返回条件、TRY300 移出 try、TRY400 换 `logging.exception`；5 处有意为之 noqa 带注释：failover/评估台宽捕获、pydantic 惯用 ValueError、测试模板按行列举、文档本地日期戳）
- vitest coverage 接入：`@vitest/coverage-v8@3.2.4`、`npm run coverage` 脚本、vite.config.ts 阈值 `statements 76 / branches 74 / functions 78 / lines 76`（基线实测 79.07/76.54/82.15/79.07 下方 2-3 点，防回归底线而非目标值）
- CI 更新：backend job 在 pytest 前加 `ruff check` 步骤；frontend job 用 coverage 运行替代纯 test；checkout/setup-node v4 → v5（消除 Node 20 弃用注记）
- 首跑核验（gh CLI）：36821205442 completed/success，frontend 34s ✓ backend 27s ✓

### Out of scope

- black 全量格式化（实测 65 文件漂移，属单独批次，避免与 lint 批次混入巨大 diff）
- 前端 eslint（当前零配置，引入与存量清理需要独立批次）
- PEP 695 泛型与 StrEnum 迁移（运行时语义敏感，随功能批次顺手做）

## 设计要点

- lint 门禁放 pytest 之前：5 秒级失败反馈，避免等 25 秒测试后才报风格问题
- 豁免必须写理由：每条全局 ignore 与每个 noqa 都带约定说明，防止豁免无限扩散
- 覆盖率阈值取"实测基线 − 2~3 点"：允许正常重构波动，拦住断崖式下降；配置内注释基线日期，供后续抬线参考

## 测试

- `uv run ruff check api tests tools` → All checks passed
- `npx vitest run --coverage` → 108 passed，四项指标均高于阈值
- `npx tsc --noEmit` → 0 error；`uv run pytest tests` → 224 passed / 2 skipped
- CI workflow YAML 解析校验（branches=[main,dev]、backend 5 步含 Lint、frontend 跑 coverage）
