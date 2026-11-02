# 2026-10-03 PRD 升版 v0.5 与 API 文档进度

第九批（纯文档批次：PRD v0.5 重写 + `docs/api.md` 新建 + README 文档入口）完成，是
`2026-10-01-black-formatting-progress.md`、`2026-10-01-ci-coverage-lint-gates-progress.md`
之后文档线的收口，对应审计报告 Schedule Later 第 21 项与 Documentation 维度（第 13 节）。
Trellis 任务：`.trellis/tasks/10-03-prd-v05-api-docs`。本批后全门禁：
**pytest 540 passed / 9 skipped（覆盖率 88.49%，门禁 87）/ ruff All checks passed /
black 181 files unchanged / tsc 0 error / vitest 15 文件 107 passed /
前端覆盖率 Stmts 85.97 · Branch 77.42 · Funcs 84.02 · Lines 85.97（阈值 76/74/78/76）**——
与基线逐项一致，证明生产代码零改动。

## 交付物

- **docs/prd.md（v0.5 重写）**：按 design 第 3 节映射表逐节执行——§2.3 非目标移出
  "语音识别"（保留"发音打分"）；§7 技术方案重写（PostgreSQL + SQLAlchemy + Alembic、
  Redis + RQ 双队列、mock/live 双运行时、签名访客 Cookie、Deepgram），删除
  "第一版允许先使用内存存储或 mock 数据"；§4 补流式回复 / 语音练习 / 学员档案 /
  LLM 复盘 / 场景文案下发 / 12MB 请求体门与 202；§10 验收补功能与工程门禁数字；
  §11 v0.1–v0.4 标注完成态 + v0.5 阶段意图四候选（档案读取 API 与前端进度页、
  LLM ReviewCopy 生产消费、评测驱动提示词修正、OTel/Langfuse 可观测性），注明
  "进度归 docs/versions/ 与 docs/control 控制面，PRD 不做 changelog"；修复 §7–§10
  内部编号错位（旧文档 7.1 写成 6.1 等）。自检 grep："第一版暂不做""内存存储或
  mock 数据""第一版允许"零命中。
- **docs/api.md（新文件）**：design 第 2 节十章节全齐（总览 / 认证与身份 / 端点清单 /
  信封与错误码 / 限流 / SSE / 202 轮询 / 游标分页 / 请求体上限与 X-Request-ID /
  健康端点），think 代理特例单列第 11 节（OpenAI 风格错误、模型白名单、SSE 透传
  的偏离细节放 §1 会让总览膨胀）。全文数值只从 config.py / exceptions.py /
  auth_rate_limit.py / contracts 摘取，每节附代码出处路径。
- **README.md**："部署"小节后新增"文档"小节（PRD / API 参考 / 部署手册三个链接），
  其余章节零改动。
- **docs/features/prd_v05_api_docs/feature.md**：核心验收物为"声明 ↔ 代码出处"
  对照表，10 张主题表覆盖端点清单 / 错误码 / 身份 / 限流配额（值 ↔ config 键名）/
  SSE 事件序 / 202 字段 / 游标格式 / 请求体上限与 X-Request-ID / 健康端点 / think 代理。

## 核对发现（清单与代码不一致处）

1. **auth 端点数 9 而非 8**：任务 design.md §2 写"auth 8"，`grep @router` 实测 9
   （README 既有"API 概览"表也少列 resend-verification）。按派发指示以 grep 为准，
   api.md §3 写 9；README 的 API 概览表由主会话在本批补上 resend-verification 行
   （README 属本批允许改动范围）。
2. **think 代理白名单空值语义**：`_validate_proxy_payload` 在 `DEEPGRAM_AGENT_THINK_MODEL`
   为空时跳过校验；因生产门控（validate_runtime）强制该值非空，不构成暴露面，
   api.md 按此精确表述。
3. 其余清单条目与代码逐条一致。

## 对照表抽查（审查门）

按 implement.md 审查门随机抽 5 条声明回读代码复核，全部命中：

| 声明 | 复核结果 |
| --- | --- |
| think_proxy 120/300s（config 键 `think_proxy_limit` / `think_proxy_window_seconds`） | ✓ config.py 两键值与 deepgram.py `consume(action="think_proxy", key=session_id)` 一致 |
| voice_bootstrap 5/3600s + IP 25/3600s | ✓ config.py `voice_bootstrap_limit` / `voice_bootstrap_ip_limit`；窗口常量 `VOICE_BOOTSTRAP_WINDOW_SECONDS=3600` |
| auth refresh 20/300s | ✓ auth_rate_limit.py `DEFAULT_AUTH_RATE_LIMITS["refresh"]` |
| 413 信封 code 1001、message "Request body too large"、不带 X-Request-ID | ✓ middleware.py `BODY_TOO_LARGE_MESSAGE` + `_send_rejection`（FileTooLargeError.code）；main.py 中间件顺序注释 |
| SSE 响应头 Cache-Control: no-cache、X-Accel-Buffering: no | ✓ sessions.py `stream_reply_to_session` StreamingResponse headers |

## 决策记录

- **重写而非增量 patch**（design D1）：漂移是系统性的（非目标 / 技术方案 / 验收标准
  三处方向性过时），补丁会留下缝合文档；历史演进由 docs/versions/ 承载。
- **api.md 十一节而非十节**：think 代理的 OpenAI 风格错误协议与统一信封差异大，
  塞进 §1"非信封端点清单"一行带不动细节；单列 §11 保持十章节结构完整。
- **对照表出处用"符号名"而非行号**：行号随代码演进漂移，config 键名 / 函数名 /
  类名可 grep 直达，腐化速度慢一个量级。
- **README API 概览表已顺手修**：派发给子代理时约束"其余章节一律不动"以控制爆炸半径；
  主会话审阅后确认该表属 README 文档面且仅差一行，本批直接补上 resend-verification，
  不留已知过时表过夜。

## 门禁复跑（与基线逐项对照）

| 门禁 | 基线 | 本批 | 一致 |
| --- | --- | --- | --- |
| pytest | 540 passed / 9 skipped | 540 passed / 9 skipped | ✓ |
| 覆盖率 | 88.49%（门禁 87） | 88.49% | ✓ |
| ruff | All checks passed | All checks passed | ✓ |
| black --check | 全部 unchanged | 181 files unchanged | ✓ |
| tsc --noEmit | 0 error | 0 error | ✓ |
| vitest | 107 passed（15 文件） | 107 passed（15 文件） | ✓ |
| 前端覆盖率 | 85.97 / 77.42 / 84.02 / 85.97 | 85.97 / 77.42 / 84.02 / 85.97 | ✓ |

## 留守事项

- 控制面登记（agent-control-plane.json 追加本 feature + latest_snapshot 更新 +
  agent_ops render/check）由主会话提交前执行，本批未动 docs/control/。
- PRD §11 v0.5 四候选逐项立项时补任务工件；不写时间表。
