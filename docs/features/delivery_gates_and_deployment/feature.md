# 交付门禁与部署（delivery_gates_and_deployment）

> 审计报告 Release 维度 + Finding 13/14 修复。
> Trellis 任务：`.trellis/tasks/10-02-delivery-gates-deployment`。

## 目标

发布阻断项收口：后端无覆盖率门禁（224→456 个测试无回归护栏）、前端 `build` 不做类型检查、`requirements.txt` 与 pyproject 双事实源漂移、无 Dockerfile/compose/部署手册、`.gitignore` 的 `tests/*`/`docs/*` 宽忽略让新文件对 git status 不可见（多批次被迫 force-add，最坏情况新测试静默漏提交）。

## 实现说明

### 1. 后端覆盖率门禁（F13a）

- `pytest-cov` 入 dev 组；pyproject `[tool.coverage.run] source=["api"]` 与 `[tool.coverage.report] fail_under=87`——阈值与口径集中在 pyproject，CI 与本地同源。
- 基线为 2026-10-02 实测 88.12%（4656 语句 / 553 未覆盖），门禁取 87 留环境波动缓冲；CI backend 步骤改为 `uv run pytest tests --cov=api`。

### 2. 前端 build 接类型检查（F13b）

`package.json` 的 `build` 从 `vite build` 改为 `tsc --noEmit && vite build`——类型错误不再能进入 dist；实测构建通过。

### 3. 依赖单事实源（F14）

`requirements.txt` 删除（与 pyproject 漂移：fastapi 0.115 vs ≥0.135）；安装口径统一为 `uv sync --frozen`（README 本就是 uv-first，无引用残留）。

### 4. Dockerfile + compose + 运行手册（Release）

- `infra/docker/Dockerfile`：python:3.12-slim + 锁定版本 uv，`uv sync --frozen --no-dev --no-install-project`（依赖层缓存友好）；api 与 RQ worker 共用镜像（worker 以 command 覆盖启动 `python -m api.tasks.worker`）；显式 `PYTHONPATH=/app` 不依赖 uvicorn 对 cwd 的隐式行为。
- `infra/docker/docker-compose.yml`：postgres:16 + redis:7 + api（`alembic upgrade head &&` 前置，迁移失败不假就绪）+ worker，健康检查依赖序。
- `docs/deployment.md` 运行手册：镜像构建、生产 17 项环境清单（指向 validate_runtime）、迁移与脏数据核查、worker 消费确认、health/readyz 语义、`--proxy-headers` 反代要求、回滚步骤。
- CI 新增 `docker` job：构建不推送（推送需 registry 凭证另行接入）。

### 5. gitignore 治理

- `tests/*` 整块删除：全目录追踪，新测试文件默认对 git status 可见（此前最坏情况=新测试静默漏提交，CI 覆盖率门禁直接失明）。
- `docs/*` 补放行 `features/versions/bugs/modules/deployment.md`；`infra/` 改 `infra/*` + `!infra/docker/`（目录级排除会挡住子目录反选）。
- 垃圾兜底仍由全局 `__pycache__/`、`*.db`、`tmp/` 等规则承担；未来真正该忽略的本地文件应显式声明而非整目录拉黑。

## 验证

- 覆盖率门禁本地实测：88.12% ≥ 87 通过；`npm run build`（tsc + vite）通过；`docker compose config` 语法校验通过（Docker 引擎未运行，镜像构建交由 CI docker job 实测）。
- `git check-ignore` 验证：tests/docs/features/infra/docker 下的新文件全部可见。
- pytest 456 passed / 2 skipped；ruff / black 全绿。

## 遗留

- 镜像 registry 推送与正式发布流水线（tag → 镜像 → 部署审批）另行接入。
- CI 增加 PG service 容器跑一次真实 Postgres 测试（SQLite/PG 差异），随 docker job 之后的批次。
