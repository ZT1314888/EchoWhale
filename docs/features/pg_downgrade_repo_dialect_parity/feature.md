# Feature: `pg_downgrade_repo_dialect_parity`

## 基本信息

- `feature`: `pg_downgrade_repo_dialect_parity`
- `status`: `feature_test_passed`
- `branch`: `dev`
- `module`: `platform_foundation`
- `cross_module`: `no`
- `owner`: `lucky`
- `updated_at`: `2026-10-07`
- `merge_target`: `module/platform_foundation`

## 背景

CI PG 批次（`ci_pg_parity_and_eslint_gate`）落地 backend-postgres job 时明确推迟了两件事，本批收口：

1. **迁移 down() 在 PG 上零验证**：该 job 只跑 `alembic upgrade head`，15 个迁移的
   `down()` 从未在真实 PG 上执行过（SQLite 口径的链测试不覆盖 PG 特有 DDL 路径，
   如 batch_alter_table 的表复制差异）；
2. **部分测试绕过方言开关**：`tests/support/dialect.py` 提供
   `ECHOWHALE_TEST_DATABASE_URL` 方言开关，但仍有测试自建硬编码 SQLite 引擎——
   它们在 PG job 里照样跑 SQLite，真实 PG 上的仓储行为（JSON 列、时区、约束回显）
   只有部分被覆盖。

## 用户故事

- 当我改动迁移脚本或模型时，我希望 CI 在真实 PG 上把 up **和** down 都跑一遍，
  这样 downgrade 路径的回归在上库前就被抓住；
- 当我写仓储代码时，我希望测试矩阵默认就在生产同款方言（PostgreSQL）上验证
  行为，这样方言差异（时区/JSON/约束回显）不再等到联调才暴露。

## 范围

### In scope

- **R1**：`tools/pg_migration_roundtrip.py` 六步往返脚本（重置 → upgrade head →
  灌种子 → downgrade base → upgrade head → 断言回 head），CI backend-postgres
  job 在 pytest 之后执行（从有数据的 schema 往下砍，FK/CASCADE/数据依赖的
  down 步骤才真正被踩到）；本地 scratch 库等价验证。
- **R2**：11 个测试文件的硬编码 SQLite 引擎全量参数化（`tests/support/engine.py`
  成为方言分支唯一归属地 + conftest 共享 fixture）；`tests/test_dialect_hygiene.py`
  防再犯守卫；5 个迁移链用例维持 `sqlite_only` 并更新理由。
- **R3**：本文档、deployment.md、两份 backend spec 更新、控制面同步。

### Out of scope（遗留）

- registry 推送流水线（等用户定 registry 目标与凭证）；
- think 一次性票据方案 B（独立立项）；
- judge 主观分歧留观察；
- CI 首跑实测（push 后用户侧确认）；
- 守卫为轻量静态扫描，已知边界（见"已知缺口"）。

## 设计要点

- 关键流程：
  - 往返脚本只认 `settings.database_url`（CI 由 DATABASE_URL env 提供）；pytest
    后的库处于任意状态（方言 fixture 按用例清理），所以脚本先重置 schema
    （drop 全部 metadata 表 + alembic_version）再经迁移链重建并灌种子，保证
    downgrade 的起点确定且带数据；
  - 方言参数化：`tests/support/engine.py` 暴露 sync/async 两个 builder（PG 分支
    连共享测试库并按用例 drop 全部 metadata 表，固定主键/邮箱因此天然隔离，
    无需把几十处断言改成随机后缀；SQLite 分支保持 tmp 文件库，行为与基线逐字节
    一致），conftest 提供 `dialect_engine` / `dialect_async_engine` fixture；
  - Windows 本地 PG：psycopg async 需 Selector 事件循环，conftest 的
    `anyio_backend` 统一在 PG 方言下前置 `ensure_psycopg_async_compatible_loop()`；
  - 防再犯守卫：扫描 `tests/**/*.py` 禁止 `sqlite://` / `sqlite+aiosqlite://`
    字面量，允许清单 5 项逐项写理由。
- 依赖模块：`platform_foundation`（api/db、tools、tests 基建）。
- 关键数据：种子数据单事务、FK-safe 顺序覆盖全部 13 张表（users → 凭据/令牌 →
  media → sessions → 消息/复盘/事件/语音事实 → scene_analyses → llm_usage →
  learner profile）。
- 失败时如何处理：往返脚本任何一步异常上抛（CI 步骤非零退出）；测试方言差异
  逐个修，禁止放宽生产代码语义。

## 验收标准（全部达成）

- `[x]` CI backend-postgres job 含迁移 downgrade 往返验证步骤（pytest 后执行），
  本地等价验证通过并记录（见下）；
- `[x]` PG 口径真实执行的测试数较基线显著提升（47 个用例从"PG job 里跑 SQLite"
  变为真实 PG 执行，前后对比见下），仓储层 session/media/auth/scene/learner/
  llm_usage 在 PG 上被直接覆盖；
- `[x]` sqlite_only 清单成文且每条有理由；防再犯守卫就位且两种口径都执行；
- `[x]` SQLite 口径基线不降（649/9、覆盖率 90.47% ≥ 基线 89.65%，门禁 87），
  PG 口径全绿（644/14、90.41%）；前端零改动门禁绿；ruff / black 全绿；
- `[x]` agent_ops render/check 一致；单提交。

## 测试记录

### 前后对比（核心数字）

| 口径 | 改前基线 | 改后 | 变化 |
| --- | --- | --- | --- |
| SQLite job passed / skipped | 647 / 9 | 649 / 9 | +2（守卫用例 + 往返脚本单测） |
| SQLite 覆盖率（门禁 87） | 89.65% | 90.47% | +0.82pp |
| PG job passed / skipped | 642 / 14 | 644 / 14 | +2（同上两个新用例） |
| PG 覆盖率（门禁 87） | —（上批未单独记录） | 90.41% | 门禁通过 |
| **PG job 内真实在 PG 上执行的用例** | **0**（下列测试全在 job 内跑 SQLite 文件库） | **47** | +47 |

改为真实 PG 执行的 47 个用例分布：session 仓储 13（test_session_repository.py）、
会话写路径 4（test_session_write_integrity.py）、learner profile 3、scene store 4、
media 1、llm_usage sink 7、auth service 14、mock 冒烟全链路 1。另有 2 个 fk-order
用例改用共享 fixture（本就方言感知，计数不变）。5 个迁移 down/up 用例维持
`sqlite_only`，PG 口径由往返脚本覆盖。

### PG downgrade 往返验证记录（本地 scratch 库等价验证）

- scratch 库：`echowhale_ci`（本机 PG，验证后已 DROP，沿用上批惯例）；
- 命令：`DATABASE_URL=postgresql+psycopg://…@localhost:5432/echowhale_ci
  MODEL_RUNTIME_MODE=mock uv run python -m tools.pg_migration_roundtrip`；
- 结果：六步全绿——重置 13 张表 + alembic_version → upgrade head →
  灌 13 张表种子 → **15 个 down() 全量执行成功** → upgrade head 重放 →
  断言 alembic_version == 20261007_0016 且关键表齐全。**零迁移需要修改**；
- 首跑曾暴露一个非迁移问题：种子用 `add_all` 一次 flush，UOW 在无 relationship()
  时不保证按 FK 依赖排序 INSERT（SQLite FK 默认关闭掩盖了它），PG 上
  auth_action_tokens 先于 users 发出撞 FK——改为逐条 add+flush 钉死顺序，与
  仓储层 parent-first flush 纪律同源；
- 全量 PG 口径：`DATABASE_URL=… ECHOWHALE_TEST_DATABASE_URL=…
  MODEL_RUNTIME_MODE=mock uv run pytest tests --cov=api` → 644 passed / 14
  skipped、覆盖率 90.41%。

### 方言差异修复记录（修测试断言/数据，不放宽生产语义）

- scene store 三个用例缺 media 父行（scene_analyses.media_id 的 FK 在 PG 真实
  强制，SQLite FK 默认关闭而放过）——补 `_save_media_parent`，对齐同文件 cascade
  用例既有形态；
- scene store 时间戳断言改为显式方言分支（PG timestamptz 回读带 tzinfo，SQLite
  naive）；
- mock 冒烟 `_prepare` 补 `engine.dispose()`：psycopg async 连接绑定创建它的
  loop，`asyncio.run` 的 loop 关闭后不清理池会让 TestClient 复用到跨循环死连接。

### sqlite_only 清单（5 项，均在 tests/db/test_session_write_integrity.py）

| 用例 | 理由 |
| --- | --- |
| 迁移 0011 up/down 可逆性 | 迁移链回归锁定 SQLite 口径；PG 口径的 up/down 往返由 CI backend-postgres job 的 `tools.pg_migration_roundtrip` 步骤（含种子数据）在真实 PG 上覆盖 |
| 迁移 0012 llm_usage up/down | 同上 |
| 迁移 0014 展示名列 up/down | 同上 |
| 迁移 0015 usage 归因列 up/down | 同上 |
| 迁移 0016 voice fact token_generation up/down | 同上 |

### 门禁复跑（提交前实测）

- SQLite：`MODEL_RUNTIME_MODE=mock uv run pytest tests --cov=api -q` → 649 passed
  / 9 skipped、90.47%；`uv run ruff check api tests tools`、
  `uv run black --check api tests tools` 全绿；
- 前端零改动：`npm run lint` 零输出、`npm run typecheck` 绿、`npm run coverage`
  → vitest 115 passed、覆盖率 86.35/77.84/84.1/86.35 全过阈值（76/74/78/76）；
  `frontend/` 零 diff。

### 已知缺口（P2 备忘）

- 守卫是轻量静态扫描：`sqlite+pysqlite://`、裸 `"sqlite"`、运行时字符串拼接、
  非 .py 文件不在覆盖内（新测试最自然的写法是字面量 URL，现实风险低）；
- `tests/modules/test_scene_cache.py:125` 残留既有裸 `anyio_backend` 覆写（该文件
  零触库，无 PG 风险，留后续批清理）；
- `test_scene_analysis_store.py` 部分用例末尾 `engine.dispose()` 与 fixture
  teardown 重复（幂等无害）。

## 控制面同步

- `docs/control/agent-control-plane.json` 已加 `pg_downgrade_repo_dialect_parity`
  行（`feature_test_passed`）；
- 同步后运行：`uv run python -m tools.agent_ops render`；
- 校验：`uv run python -m tools.agent_ops check`。

## 合并与关闭

- 本批随 dev 单提交合入；CI 首跑实测由用户 push 后确认（见遗留），确认无误后
  可写 `merged_to_module`；
- `closed` 待 registry 推送流水线等遗留项另行立项后统一回顾；
- 相关文档：`docs/deployment.md`（CI PG job 往返验证说明）、
  `.trellis/spec/backend/database-guidelines.md`（迁移往返口径）、
  `.trellis/spec/backend/quality-guidelines.md`（方言 helper 与守卫）。
