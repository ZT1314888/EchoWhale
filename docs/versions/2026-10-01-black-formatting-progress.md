# 2026-10-01 black 全量格式化 + CI 格式门禁进度

第八批（留守批次：black 全量格式化 + CI 格式门禁）完成，是 `2026-10-01-ci-coverage-lint-gates-progress.md` 的直接后续。前置核验：dev 与 origin/dev 同步于 997a5c5、工作区干净。本批后全门禁：**black --check 零漂移（115 files unchanged）/ ruff All checks passed / pytest 224 passed + 2 skipped / tsc 0 error / vitest 108 passed / coverage Stmts 79.07 · Branch 76.54 · Funcs 82.15 · Lines 79.07**——除新增 black 这道门外，其余五道数字与基线逐项一致。

## black 接入

- 配置：`pyproject.toml` 增加 `[tool.black]`，`line-length = 100`，与 `[tool.ruff]` 对齐，注释写明对齐理由
- 漂移口径修正：任务前置记录的"65 文件漂移"为旧数字；本批实测默认配置（88）51 文件漂移 / 64 不变，配 line-length=100 后降为 **25 文件漂移 / 90 不变**——长行不再被 black 二次折叠，重排 diff 直接减半
- 执行：`uv run black api tests tools`（范围与 ruff 完全一致，frontend 不动），25 文件 reformatted；抽查 diff 全部为折行/换行等纯机械调整，无语义改动
- noqa 安全性：重排后 ruff All checks passed，证实 noqa 注释仍附着在原违规行，black 与 ruff 对 noqa 归属规则一致

## CI 工作流

- backend job 在 **Lint (ruff)** 步骤旁增加 **Format (black)**：`uv run black --check api tests tools`，同样位于 pytest 之前（秒级失败反馈）
- 触发分支维持 `[main, dev]`，frontend job 不变

## 门禁复跑（与基线逐项对照）

| 门禁 | 基线 | 本批 | 一致 |
| --- | --- | --- | --- |
| pytest | 224 passed / 2 skipped | 224 passed / 2 skipped | ✓ |
| ruff | All checks passed | All checks passed | ✓ |
| tsc --noEmit | 0 error | 0 error | ✓ |
| vitest | 108 passed（15 文件） | 108 passed（15 文件） | ✓ |
| coverage | 79.07 / 76.54 / 82.15 / 79.07 | 79.07 / 76.54 / 82.15 / 79.07 | ✓ |
| black --check | （未接入） | 115 files unchanged | 新增门 |

## 决策记录

- **line-length=100 而非默认 88**：与 ruff 保持一致是硬要求，同时把一次性重排从 51 文件压到 25 文件
- **一次性大 diff 不拆散**：格式化提交独立成批、单独成 commit，评审时整体跳过即可，拆散反而污染后续功能批次
- 过程小坑再确认：`cd frontend` 后 CWD 残留导致 `git diff <path>` 报 ambiguous argument（`&&` 链外的下一条命令仍执行），回根目录重跑即恢复；落盘补丁脚本用完即删，避免上批"根目录残留补丁脚本"复现

## 留守事项

- 前端 eslint 引入批次
- 内联分析路径进度真实化、语音逐轮反馈（后端管线）、系统级 smoke、PRD 刷新（原队列不变）
