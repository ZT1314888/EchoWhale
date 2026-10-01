# 2026-10-01 CI coverage + lint 门禁进度

第七批（留守队列第 1 项：coverage 阈值 + lint 接 CI）完成。前置核验：gh CLI 确认 dev 分支首次 Actions 实跑 **completed/success**（run 36821205442，frontend 34s ✓ / backend 27s ✓，即上一批提交 21d643d 的实跑）。本批后全门禁：**ruff All checks passed / tsc 0 error / vitest 108 passed / coverage 阈值达标（Stmts 79.07 / Branch 76.54 / Funcs 82.15 / Lines 79.07）/ pytest 224 passed + 2 skipped**。

## ruff 接入（189 → 0）

- 依赖与配置：`ruff>=0.16.9` 入 dev 组；`extend-select = I/B/UP/RUF/SIM/TRY/FURB/DTZ/BLE`；`flake8-bugbear.extend-immutable-calls` 豁免 `fastapi.Depends/File/Query`（52 处 B008 逐一核实全部为 DI 官方写法）
- 仓库约定豁免（每条带理由写进 pyproject）：`RUF001/002/003`（中文全角标点，326 处）、`TRY003`（消息式异常约定，124 处）、`UP042/046/047`（str-Enum 与旧式 Generic 运行时语义敏感，8 处，单独批次迁）
- 清零路径：154 处 `--fix` 自动修（import 排序 ×57、`datetime.UTC` ×33、quoted-annotation 等）+ 8 处人工裁决——修复 3（SIM103 条件直返、TRY300 返回移出 try、TRY400 `logging.exception`）、noqa 带注释 5（failover 与评估台的 BLE001 宽捕获、pydantic 惯用 ValueError 的 TRY004、测试模板 join 的 FLY002、文档本地日期戳的 DTZ011）
- 154 处自动修后 pytest 保持 224 全绿，证明 import 重排序无循环依赖副作用

## vitest coverage 接入

- `@vitest/coverage-v8@3.2.4`（与 vitest 3.2.4 对齐）+ `npm run coverage` 脚本
- `vite.config.ts`：provider v8、include `src/**`、exclude `main.tsx/test/类型声明`、reporter text+html、阈值 `76/74/78/76`（基线 79.07/76.54/82.15/79.07 减 2-3 点，配置内注释基线日期供抬线）
- CI frontend job 由纯 `npm test` 换成 `npm run coverage`（本地快捷跑保留 `npm test`）

## CI 工作流

- backend：uv sync → **Lint (ruff)** → sqlite 建表 → pytest（lint 放测试前，5 秒级失败反馈）
- frontend：checkout@v5 / setup-node@v5（消除首跑的两条 Node 20 弃用注记）→ npm ci → typecheck → coverage
- 触发分支维持 `[main, dev]`

## 决策记录

- **black 暂不进门禁**：`black --check` 实测 65 文件漂移，全量格式化的巨型 diff 不该混进 lint 批次，单独排批一次到位
- **前端 eslint 暂不引入**：当前零配置零依赖，引入 + 存量清理 + 规则调优需要独立批次
- 过程教训再实锤：① workflow 步骤里带 `name:` 的行其 `uses:` 没有短横线，锚点照 `- uses:` 写必然失配；② heredoc 反斜杠吞噬第三次出现（`"\\n"` 变真换行），小补丁也一律 Write 落盘；③ 一条 `&&` 链在断言处断裂后，`;` 分隔的后续命令仍会执行——本批出现 tsc=1 假读数与 vitest 从仓库根误跑 28 文件，排查时先确认 CWD 与链路断裂点再下结论

## 留守事项

- black 全量格式化批次（65 文件）
- 前端 eslint 引入批次
- 内联分析路径进度真实化、语音逐轮反馈（后端管线）、系统级 smoke、PRD 刷新（原队列不变）
