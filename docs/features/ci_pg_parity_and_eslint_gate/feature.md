# Feature: `ci_pg_parity_and_eslint_gate`

## 基本信息

- `feature`: `ci_pg_parity_and_eslint_gate`
- `status`: `feature_test_passed`
- `branch`: `dev`（交付门禁批次按既有惯例随 dev 推进）
- `module`: `platform_foundation`
- `cross_module`: `yes`（前端门禁联动 `frontend_app`）
- `owner`: `lucky`
- `updated_at`: `2026-10-07`
- `merge_target`: `module/platform_foundation`

## 背景

生产库是 PostgreSQL，但后端测试至今只在 SQLite 上被 CI 验证——迁移链与仓储行为
（FK 强制、约束、JSON 列）从未在真实 PG 上跑过，"CI 绿"与"生产库行为"之间存在
平价缺口。前端只有 typecheck 没有 eslint：hooks 依赖数组错误（exhaustive-deps）
与 fast-refresh 边界问题 tsc 抓不住。另有一个尾巴：167f5f1 删除
SessionSummary.liveHint 后，SampleScene.liveHint 成零消费死数据。

## 用户故事

- 当我推送迁移或仓储改动时，我希望 CI 在真实 PostgreSQL 上验证迁移链与 FK 写入
  顺序，这样 SQLite 特有行为不会在上线后才暴露。
- 当我修改前端 hooks 时，我希望 lint 门禁在 CI 拦住依赖数组错误与刷新边界问题，
  这样回归在合入前而不是排查现场被发现。

## 范围

### In scope

- R1：CI 新增 `backend-postgres` job（postgres:16 service + pg_isready healthcheck；
  `uv sync --frozen` → `uv run alembic upgrade head`（真实 PG 上验证迁移链，本
  job 核心价值）→ 全量 `uv run pytest tests --cov=api`，覆盖率门禁同 pyproject
  fail_under=87）。SQLite backend job 保持不动（快速反馈层）。
- R1：方言感知测试处置——`tests/support/dialect.py`（`ECHOWHALE_TEST_DATABASE_URL`
  显式方言开关 + `enforce_foreign_keys` 方言感知 FK 强制 + `to_psycopg_url` 归一化
  + Windows psycopg async Selector loop 处理）、`sqlite_only` 标记（PG 方言下 skip
  且理由成文）、FK 顺序测试改写为方言无关（PG 上真实 FK 强制验证同一意图）。
- R2：eslint 10 flat config（typescript-eslint recommended + react-hooks v7
  recommended + react-refresh vite 预设）、`npm run lint` script、CI frontend job
  Lint 步骤前置；存量 9 个违规逐条处置（含 UserMenu 条件 useEffect 真 bug 修复）。
- R3：SampleScene.liveHint 零消费清理（数据 3 处 + 类型 1 处）。

### Out of scope（遗留）

- registry 推送流水线（需先定 registry 目标与凭证）。
- think 一次性票据（设计量大，独立立项）。
- judge 主观分歧留观察。
- PG 口径的迁移 downgrade 验证与全仓储 PG 参数化（更大改造，后续批次评估）。

## 设计要点

- 关键流程：PG job 的 `DATABASE_URL` 与 `ECHOWHALE_TEST_DATABASE_URL` 同指 service
  库——前者驱动 alembic（`api/migrations/env.py` 读 `settings.database_url`），后者
  是测试方言开关。**方言源绝不取 `settings.database_url`**：本地 .env 指向 dev 库，
  以其为源会让本地测试写脏 dev 库并改变本地基线。
- SQLite 专属测试处置清单（PG job 下显式 skip，理由成文）：
  - `tests/db/test_session_write_integrity.py` 的 4 个迁移 down/up 可逆性用例
    （`sqlite_only`：可逆性锁 SQLite 口径，PG 口径由 `alembic upgrade head` 承担）。
  - FK 顺序测试（auth 2 例 + session 1 例）不改 skip 而是方言化改写：SQLite 维持
    PRAGMA 强制，PG 直接依赖真实 FK 强制；ID/邮箱/token hash 加 per-test 随机后缀
    防共享库残留。`tests/db/test_scene_analysis_store.py` 的 PRAGMA helper 换为
    `enforce_foreign_keys`（URL 维持自建 SQLite）。
  - 其余 tests/db 仓储测试自建 SQLite URL、自包含，两 job 均运行，覆盖率口径一致。
- Windows 本地陷阱：psycopg async 不可用 ProactorEventLoop——`ensure_psycopg_
  async_compatible_loop()` 在 PG 方言下切 Selector（CI Linux 默认即 Selector）。
- 前端 eslint：禁止全局关规则；豁免逐条附理由（测试文件/工具文件的 fast-refresh
  边界豁免、AuthProvider 的 useAuth+Provider 同文件组织豁免）。
- 依赖模块：`platform_foundation`（CI/工具链）× `frontend_app`（lint 门禁）×
  `session_orchestration`（FK 顺序测试归属行为域）。
- 失败处理：PG job 失败即红（与 backend job 同门槛）；如 CI 不稳定可单独禁用
  PG job，不影响其余门禁。

## 验收标准

- `[x]` CI 新增 PG job：alembic 链真实 PG upgrade + 全量测试绿；SQLite 专属测试
  显式跳过且理由成文；本地等价验证有记录（本机 PG 独立库 echowhale_ci 全流程，
  见下方测试记录）。
- `[x]` eslint：flat config + `npm run lint` + CI Lint 步骤落地；存量 9 违规清零；
  无全局关规则。
- `[x]` liveHint 零残留（grep 零命中）；前端四项覆盖率阈值不降。
- `[x]` 全量门禁绿：后端 635 passed / 9 skipped、覆盖率 89.56%、ruff/black 全绿；
  前端 lint 清零、typecheck 绿、vitest 115 passed、coverage
  86.35/77.81/84.1/86.35 全过阈值（76/74/78/76）；agent_ops check 一致；单提交。

## 测试记录

- `feature_test_passed` 证据（2026-10-07）：
  - SQLite 口径（现状基线，方言开关未设）：`MODEL_RUNTIME_MODE=mock uv run pytest
    tests --cov=api` → 635 passed / 9 skipped，覆盖率 89.56%（门禁 87）——与批次
    基线一致，方言机制零影响。
  - PG 口径（本地等价验证，Docker 未运行，用本机真实 PG 独立库 echowhale_ci）：
    `alembic upgrade head` 全链 0001→0015 通过（alembic_version=20261006_0015，
    14 张业务表建成）；`DATABASE_URL + ECHOWHALE_TEST_DATABASE_URL + MODEL_RUNTIME_
    MODE=mock uv run pytest tests --cov=api` → 631 passed / 13 skipped（13 = 9 既有
    skip + 4 个 sqlite_only 迁移用例），覆盖率 90.01%，3 个 FK 顺序用例在真实 PG
    上通过。验证后 scratch 库已清理。
  - 覆盖率分母差异说明：PG 口径 5297 语句 vs SQLite 5573，差 276 全部为 alembic
    迁移脚本模块（PG 口径下迁移测试 skip 后不再 import 进分母；迁移链验证由 CI
    的 `alembic upgrade head` 步骤承担），两口径均过门禁。
  - 前端：`npm run lint` 零输出；`npm run typecheck` 绿；`npm run test` 16 文件
    115 passed；`npm run coverage` 115 passed + 四阈值全过。
  - agent_ops：控制面事实源更新后 `render` + `check` 一致。
- 主要测试命令：见上；CI PG/docker job 本机 Docker 引擎未运行无法全真跑，workflow
  YAML 已过语法解析校验，以推送后的 GitHub Actions 实测为准。
- 已知缺口：
  - PG 口径的迁移 downgrade 未在 CI 验证（本地亦未跑，避免对 scratch 库反复
    DDL），后续批次评估。
  - 仓储行为 PG 平价目前覆盖 FK 顺序三用例；全仓储 PG 参数化属更大改造，留后续。
  - coverage 模式下 TextComposer 测试偶发一例失败（`npm run test` 与复跑 coverage
    均通过，疑似 jsdom 并行偶发），未复现第二次，留观察。
