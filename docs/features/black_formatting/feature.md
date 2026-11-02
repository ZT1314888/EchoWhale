# Feature: `black_formatting`

## 基本信息

- `feature`: `black_formatting`
- `status`: `feature_test_passed`
- `module`: `platform_foundation`
- `cross_module`: `no`（仅后端 `api/tests/tools` 与 CI backend job，`frontend/` 不动）
- `owner`: `lucky`
- `updated_at`: `2026-10-01`
- `merge_target`: `module/platform_foundation`

## 背景

上一批（`ci_coverage_lint_gates`）接入 ruff 与 coverage 门禁时决策：black 全量格式化单独排批，避免巨型机械 diff 混进 lint 批次。`black>=26.5.1` 早已在 dev 依赖组，但从未实际执行；本批开工前以默认配置（line-length=88）实测 51 文件漂移 / 64 不变（上一批留痕的 65 文件是重排前旧口径，总文件数 115 一致）。

## 用户故事

- 当我提交一段不符合 black 风格的后端代码，我希望 CI 的 Format (black) 步骤与 ruff 一样在 pytest 之前直接拦下。
- 当两位协作者各自手写格式，我希望仓库只认 black 的唯一答案，评审 diff 里不再出现纯格式争论。

## 范围

### In scope

- `pyproject.toml` 增加 `[tool.black]`：`line-length = 100`，与 `[tool.ruff]` 的 line-length 对齐（配置后漂移从 51 降到 25 文件，一次性重排 diff 显著缩小）
- `uv run black api tests tools` 全量重排（范围与 ruff 完全一致）：25 文件 reformatted / 90 unchanged，纯机械 diff，一次性做完不拆散
- CI backend job 在 Lint (ruff) 步骤旁增加 Format (black)：`uv run black --check api tests tools`
- 复跑全部既有门禁，数字与基线逐项一致，作为"纯格式化、无语义变更"的证明

### Out of scope

- `frontend/`（JS/TS 侧格式化由既有前端门禁管，本批不引入 prettier）
- pre-commit hook 接入（如需本地强制格式化，另排批次）
- black 与 ruff 规则冲突调优（当前实测零冲突，noqa 附着关系未受重排影响）

## 设计要点

- line-length 对齐到 100：black 不再把 ruff 放行的长行再折一遍，重排范围减半（51 → 25 文件），两个工具对同一文件不会互相翻烙饼
- 格式化门禁放 pytest 之前、紧邻 Lint (ruff)：秒级失败反馈，不等 25 秒测试跑完才报格式问题
- 本批零测试增删、零行为变更：五道门禁数字必须与基线完全一致，这是"格式化未触语义"的验收证据

## 测试

- `uv run black --check api tests tools` → 115 files would be left unchanged（零漂移）
- `uv run ruff check api tests tools` → All checks passed（noqa 附着未受重排影响）
- `uv run pytest tests` → 224 passed / 2 skipped（与基线一致）
- `cd frontend`：`npm run typecheck`（tsc --noEmit）→ 0 error；`npm run coverage` → 108 passed（15 文件），Stmts 79.07 / Branch 76.54 / Funcs 82.15 / Lines 79.07（与基线一致）
- push 后 gh CLI 确认 dev 分支新 run：backend job 实跑含 Format (black) 步骤且双 job 全绿
