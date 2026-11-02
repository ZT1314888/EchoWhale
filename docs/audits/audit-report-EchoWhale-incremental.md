# EchoWhale 历史增量复审（2026-10-07）

> 历史快照：审计日期 2026-10-07，于 2026-11-02 归档。以下结论、测试数量、路径与行号仅对应当时版本，不代表当前状态；原始发现与评分保留。当前验证见[发布记录](../features/repository_publish_refresh/feature.md)。本机审计元数据保留在忽略目录 `.claude/audits/`，不随报告发布。

**Project:** EchoWhale
**Audit mode:** incremental（git 范围 `3849a1b..HEAD`，2026-10-01 全量审计后的修复纪元）
**Date:** 2026-10-07
**Reviewer:** ZCode (GLM-5.3-Flash)

---

## 1. Executive Summary

本次增量复审覆盖 2026-10-01 全量审计（Overall 6.5 B）之后的全部 23 个提交：209 个文件、+20272/-2503 行。这个纪元的工作分三类：**把上轮 21 条发现中的大部分真正修掉**（访客 Cookie 签名化、上传流式+全局 body 门、生产门控反转、媒体归属校验、反馈降级、position 唯一约束、语音收口 append-only、限流 Redis 化、max_tokens 预算+usage 账本、request-id+/readyz、OTel 三层 span、覆盖率门禁、Dockerfile/compose/部署手册、提示词工程+LLM 复盘、学员档案、场景文案单一事实源、死代码清理）；**在此基础上新增产品面**（档案读 API、/progress 页、display names、评测台）；**并把这批做法沉淀为 spec 不变量**（`.trellis/spec/backend/quality-guidelines.md` 的五条 2026-10 契约）。

总体判断：**修复质量高于"打补丁"水准，接近"批次工程"水准**。六条关键不变量逐条验证全部成立——server-attested identity（验签后派生键、IP 键只取 TCP 对端）、bounded bodies（纯 ASGI body 门 + 64KB 分块上传，无一处 `await file.read()` 整包）、orchestration failure policy（反馈/复盘/档案三个增强分支全部显式降级且 `CancelledError` 不吞）、fail-closed env gate（白名单外一律生产清单 17 项）、bearer 令牌生命周期契约（gen claim + 持久代数 + 统一 401 错误体 + bool 排除）。迁移链 0010→0016 单线、downgrade 对称、0016 用 server_default 与代理侧 fail-closed 自洽。实测 `pytest 649 passed / 9 skipped`（覆盖率 90.47% ≥ 门禁 87）、ruff/black 全绿。

本轮新发现 9 条（0 Critical / 0 High / 3 Medium / 4 Low / 2 Info，全部 Confirmed），没有一条动摇修复批次的方向，但有三类值得下一批处理：**破坏性工具缺程序化护栏**（pg_migration_roundtrip 本地误跑即清库，本机 .env 的 DATABASE_URL 正指向 dev PG）；**限流 Lua 脚本零真实执行覆盖**（测试 fake 模拟 EVAL 语义而非执行 Lua，安全控制在其真实运行层未被测过）；**语音收口与文本回复的并发处理不对称**（save_reply_turn 有唯一约束重试，finalize_voice_session 没有）。另有上轮 3 条 Schedule-Later 项未动（F9 历史 INNER JOIN、F16 数据保留/账号删除、F21 语音 hook 668 行），属遗留而非回归。

### Score Dashboard（回访评分，仅限增量范围）

```
Security        █████████░  8.5  A   五条安全不变量逐条验证成立；残余：Lua 零执行覆盖、think 上游配置不在启动门控
Stability       ████████░░  8.0  A   三分支降级+唯一约束+append-only 全部落地；残余：finalize 并发不对称、0011 脏数据升级
Performance     ████████░░  8.0  A   max_tokens 全接线、usage 落库、流式上传、复盘 5s 有界等待；无真实压测数据
Testing         █████████░  8.5  A   224→649 测试、覆盖率门禁 87（实测 90.47）、CI 真 PG 平价；残余：Lua 假执行、并发用 seam 模拟
Maintainability █████████░  8.5  A   死代码清空、文案单一事实源、方言层收敛、部署手册+API 文档齐备
Design          █████████░  8.5  A   Protocol+factory 纪律在新模块全保持、测试缝隙刻意设计、归因 ContextVar 论证完整
Release         ████████░░  7.5  A   Dockerfile/compose/runbook/PG 往返进 CI；残余：compose 开箱必失败、root 容器、CI 两 job 未实测
─────────────────────────────────────
Overall         ████████░░  8.2  A
```

每个维度 0.0–10.0，**分数越高越好（10 = 干净，0 = 屎山）**。分数为评审判断而非机械扣分；仅对增量范围内触及的维度给出回访评分，七维全部被本轮变更触及故全部回访。Coverage 限制见 Coverage Matrix。

### Finding Statistics

| Severity | Count | Confirmed | Suspected |
|----------|-------|-----------|-----------|
| Critical | 0 | 0 | 0 |
| High | 0 | 0 | 0 |
| Medium | 3 | 3 | 0 |
| Low | 4 | 4 | 0 |
| Info | 2 | 2 | 0 |
| **Total** | **9** | **9** | **0** |

## 2. Change Summary 与 Project Map

### Change Summary（增量模式附加节）

- Total files changed: 209
- Lines added: 20272；Lines deleted: 2503
- Commits in range: 23（3849a1b 之后全部提交）
- Authors: Lucky（单一作者）

### Change Categories

| 类别 | 文件数 | 说明 |
|------|--------|------|
| 测试（tests/） | 65 | 新增方言支撑层、写完整性、限流、telemetry、learner、评测台等 |
| 文档（docs/ 等） | 30 | feature 留痕 24 篇、PRD v0.5、docs/api.md、docs/deployment.md |
| 前端（frontend/） | 41 | /progress 页、learnerApi、场景文案后端化、mock 时代组件/服务删除、eslint |
| CI/基础设施（.github/、infra/） | 3 | ci.yml（PG 平价 + eslint + docker build job）、Dockerfile、compose、.dockerignore |
| 后端与根配置（api/、tools/、pyproject 等） | 70 | 安全修复 7 项、迁移 6 个、usage/档案仓储、OTel、评测台、往返工具 |

### Risk Delta

- New risks introduced: 9（本轮全部发现，见第 4 节）
- Existing risks fixed: 上轮 21 条中 18 条已修复或显式处置（F1–F8、F10–F15、F17–F20；F5 的 XFF 部分以"只取 TCP 对端 + runbook 写明 --proxy-headers"方案关闭）
- Existing risks made worse: 0（逐条核对交叉影响后未发现修复引入的恶化；上轮遗留 F9/F16/F21 保持原状）

### Test Coverage Delta

- New code with tests: 新后端模块（middleware/request_context/telemetry/rate_limit_window/llm_usage_db/learner_profile_db/learners 路由/learner_profile/review_summarizer/display names/安全签名/方言层/迁移往返）全部有对应测试文件；前端 learnerApi 有测试
- New code without tests: Dockerfile/compose（不可单测，CI build job 覆盖构建性）、pg_migration_roundtrip 的 main 流程（由 CI 步骤实测）、`configure_telemetry` 开启态 OTLP 真实导出路径（测试注入 InMemory 导出器）
- Deleted tests: mock 时代前端测试（mockApi.test.ts 等）随 mock 数据层一起删除，由针对真实 API 契约的测试替代，无净覆盖损失

### Project Map（增量后的形态）

- **入口与管线**：`api/main.py` 装配顺序 CORS → BodySizeLimit（纯 ASGI，12MB）→ RequestContext（X-Request-ID 校验/生成/回写）→ Tracing（server span，探针旁路）→ 路由；异常处理器保持 `ApiResponse` 信封；`/health`（liveness）与 `/readyz`（DB SELECT 1 + Redis PING 硬超时 + R2 仅查配置）分工明确。
- **身份与限流**：访客 Cookie 经 `sign_value/verify_signed_value`（HMAC-SHA256、恒时比较、rpartition 拆分）验签后派生 owner；限流键只出自已验证身份或 TCP 对端地址；`rate_limit_window.FixedWindowCounter` 以单次 EVAL 原子完成 INCR+首次 EXPIRE，Redis 与进程内实现共享规则工厂，LRU 容量上限防键无界。
- **编排器**（session_engine/agent.py，990 行）：reply/stream/voice 三路径统一 failure policy——教练分支失败整轮上抛，反馈/复盘/档案三增强分支显式降级（degraded=true 日志 + 占位反馈 + None 复盘回退模板）；语音 bootstrap 递增 token_generation 并签入 think 令牌。
- **数据层**：messages 表 (session_id, position) 唯一约束兜底 + save_reply_turn 两段重试；voice 收口 append-only；llm_usage 账本（归因列可空，ContextVar 在调用线程捕获后传参线程池）；learner_profiles 单行 upsert（写侧封顶 ≤9/≤12/≤10）。
- **安全边界**：媒体归属校验前置于缓存查询与场景分析派发（404 收敛）；think 代理限流先于存在性校验、生命周期校验 fail-closed；生产门控 17 项在 import 期执行。
- **风险最集中区域（本轮）**：`tools/pg_migration_roundtrip.py`（破坏性、无程序化护栏）、`api/db/session_db.py`（并发语义两路径不对称）、`api/services/rate_limit_window.py`（Lua 无真实执行覆盖）。

### Coverage Matrix

| Dimension | Coverage | Evidence inspected | Exclusions / limits |
|-----------|----------|--------------------|---------------------|
| Security | High | security.py/middleware.py/config.py/deps.py/两限流器/deepgram 路由+codec/media_service/sessions 路由/feedback 降级逐行精读；六不变量逐条比对 | 未做渗透测试与依赖 CVE 扫描；X-Request-ID 消耗方（LB 日志）未验 |
| Stability | High | session_db 写路径、agent.py 全读、migrations 0011–0016、usage sink、review_summarizer 降级链、/readyz | 未做负载/故障注入；Redis 降级路径未在真 Redis 故障下实测 |
| Performance | Medium | max_tokens 接线、流式上传分块、LRU 有界、复盘 5s 等待、usage fire-and-forget | 无真实压测；OTel 开启态开销未测量 |
| Testing | High | conftest/dialect/engine、写完整性/限流/安全/评测台测试逐读、全量套件实测 649 passed/90.47%、lint 实测 | live 评测（RUN_*_EVAL=1）未实跑（涉及真实 LLM 费用） |
| Maintainability | High | 死代码清查（rg 断链验证）、SCENE_COPY 单源、方言支撑层、docs/api.md 抽查对照 | 前端 41 文件以抽查为主（ProgressPage/learnerApi/eslint 精读） |
| Design | High | 六不变量对照 spec 原文、Protocol+factory 抽查新模块、测试缝隙设计（_read_max_position） | — |
| Release | Medium | ci.yml 全读、Dockerfile/compose/.dockerignore、pg_migration_roundtrip 全读、pyproject 覆盖率门禁、deployment.md 对照 | CI 两个新 job（PG/docker）首跑待 push 后实测（已知暂缓项，未重复报告）；未做真实部署验证 |

排除项：`frontend/node_modules`、`uv.lock` 明细、`.trellis/` 工作流脚本、二进制资源、上轮已知暂缓项（registry 推送、think 方案 B、judge travel_b1_ticket 主观分歧、dialect hygiene 静态扫描可绕过 P2、覆盖率分母 alembic 口径差——均未重复报告）。

## 3. Top Risks

1. **pg_migration_roundtrip 无程序化防误触护栏，本地误跑即清空目标库**（Medium, Release）— 本机 .env 的 DATABASE_URL 正指向 dev PG，唯一防护是 docstring 一句话。
2. **限流 Lua 脚本零真实执行覆盖**（Medium, Testing）— 测试 fake 按语义重写 EVAL，FIXED_WINDOW_LUA 文本从未被任何测试执行。
3. **finalize_voice_session 缺唯一约束冲突重试，与 save_reply_turn 不对称**（Medium, Stability）— 语音收口撞上并发文本回复时直接 500。
4. **迁移 0011 在存量重复 position 数据上升级失败**（Low, Stability）— runbook 已写人工预检 SQL，但迁移内无去重/清晰报错。
5. **compose 自称"可运行的最小拓扑"但开箱必失败**（Low, Release）— APP_ENV=production 触发 17 项门控而 compose 只注入 3 个变量。
6. **Dockerfile 以 root 运行且基础镜像仅 tag pin**（Low, Security）— 无 USER 指令，python:3.12-slim 未 pin digest。
7. **think 上游配置不在启动期 fail-closed 门控内**（Low, Release）— 生产门控查 THINK_MODEL 但不查 UPSTREAM_BASE_URL/API_KEY，缺配只在请求期 500。
8. **Redis 故障降级时限流算法静默变化**（Info, Stability）— 固定窗口（Redis）退化为滑动窗口且从跨进程退化为进程级。
9. **写完整性并发测试为 seam 模拟而非真实并发**（Info, Testing）— 诚实且确定性，但真实并发写从未被两个真任务同时执行过。

## 4. Detailed Findings

### Finding: 破坏性迁移往返工具无程序化防误触护栏，本地误跑即清库

- Severity: Medium
- Confidence: High
- Category: Release
- Status: Confirmed
- Affected area: tools/pg_migration_roundtrip.py（CI backend-postgres job 与本地共用命令）
- Evidence:
  - File: tools/pg_migration_roundtrip.py:245-258、:19、:101-107
  - Function / Module: `main()` / `_reset_schema()`
  - Relevant behavior: `main()` 直接读 `settings.database_url`（本地由 .env 提供，指向 dev/评测 PostgreSQL），`_reset_schema()` 对该库执行 `Base.metadata.drop_all` + `DROP TABLE IF EXISTS alembic_version`，随后 downgrade base 再 upgrade。唯一的防护是 docstring 第 19 行"本地必须显式 pin 到 scratch 库，禁止误触 dev 库"——纯文档约束，无任何运行时校验、确认提示或 URL 白名单。
  - Changed functions: `main`、`_reset_schema`（新增）
  - Related unchanged code: 本地 .env（DATABASE_URL 指向 dev 库）；docs/deployment.md 第 34-36 行把该命令作为标准操作宣传
- Change type: Added
- Problem: 破坏性重置脚本的目标库完全由运行时环境决定，唯一的防误触措施是文档字符串里的一句提醒，没有确认变量、参数白名单或任何运行时校验。
- Why it matters: 数据丢失脚枪——按文档照做的操作者在未 pin 环境变量时清空开发库全部 13 张业务表；"本地与 CI 同一条命令"的宣传放大了误触概率。
- Realistic failure scenario: 开发者在本地终端直接运行文档/工具 docstring 里的同一条命令 `uv run python -m tools.pg_migration_roundtrip`，.env 的 DATABASE_URL 指向 dev 库，drop_all 静默执行，用户/会话/媒体元数据全部丢失（R2 对象尚在但元数据不可恢复）。
- User-visible impact: 开发数据全损；若有人误在准生产环境执行则为生产事故。
- Minimal fix: `main()` 开头加一道明确确认门——要求 `ECHOWHALE_ROUNDTRIP_CONFIRM=1`（或 `--database-url` 显式参数且命中 scratch 库命名模式如 `echowhale_ci`），否则 raise ConfigurationError 拒绝执行。
- Better long-term fix: 把"破坏性操作必须显式确认"沉淀进 `.trellis/spec/backend/quality-guidelines.md`（与 fail-closed env gate 同族纪律），CI 步骤显式传确认变量。
- Regression test suggestion: tools 单测新增用例——未设确认变量时对非 scratch 命名的 URL 断言抛 ConfigurationError 且 `_reset_schema` 未被调用。
- Estimated effort: 30 分钟

### Finding: 限流 Lua 脚本零真实执行覆盖，测试 fake 模拟的是语义而非脚本

- Severity: Medium
- Confidence: High
- Category: Testing
- Status: Confirmed
- Affected area: api/services/rate_limit_window.py + tests/services/test_auth_rate_limit.py、test_llm_rate_limit.py
- Evidence:
  - File: tests/services/test_auth_rate_limit.py:117-147（FakeRedis.register_script 用 Python 闭包重写 INCR+首次 EXPIRE 语义，注释自认"模拟的是 EVAL 的语义契约而非 Lua 本身"）、:150-161（FlakyRedis）
  - Function / Module: `FakeRedis.register_script`；被测对象 `api/services/rate_limit_window.py:14-20` 的 `FIXED_WINDOW_LUA`
  - Relevant behavior: 全仓没有任何测试执行过真实 Lua 文本（未引入 fakeredis+lupa，CI 两个 job 均无 Redis service，.github/workflows/ci.yml 无 redis 容器）。Lua 脚本内容（ARGV 索引、EXPIRE 条件、返回值）不在任何断言路径上。
  - Changed files: rate_limit_window.py（新增）、两个限流测试（新增）
- Change type: Added
- Problem: FIXED_WINDOW_LUA 的脚本文本从未被任何测试执行——fake 客户端按注释承认是"模拟 EVAL 的语义契约而非 Lua 本身"，CI 两个 job 也没有 Redis service，Lua 内容（ARGV 索引、EXPIRE 条件）不在任何断言路径上。
- Why it matters: 安全控制（限流）在其真实运行层（Redis EVAL）零覆盖；脚本回归会带着全绿测试上线，且失败形态（静默降级）恰好绕过所有常规告警。
- Realistic failure scenario: 有人改动 FIXED_WINDOW_LUA（如把 `current == 1` 误改为无条件 EXPIRE，或 ARGV 索引错位），本地与 CI 全绿；生产上窗口 TTL 每次续增被重置或脚本抛错——后者每请求触发 RedisError 降级路径，多 worker 配额静默按进程数倍增，限流形同虚设且无 error 级告警（只有 warning 日志）。
- User-visible impact: 限流配额失真或失效，成本/滥用防线在毫秒级打开且难以察觉。
- Minimal fix: 新增一个真 Redis 集成测试（复用 tests/integration 的 RUN_* 门控模式，本地/CI 有 Redis 时执行），断言同一 key 连续 INCR 的返回序列与首次 EXPIRE 行为；无 Redis 环境保持 skip。
- Better long-term fix: CI 增加 redis service 容器（与 backend-postgres job 同构），把 Lua 路径纳入平价验证。
- Regression test suggestion: 见上；另加一条断言 `register_script` 收到的脚本文本含 `EXPIRE` 与 `KEYS[1]`（廉价的结构锁定）。
- Estimated effort: 1-2 小时

### Finding: finalize_voice_session 缺唯一约束冲突重试，与 save_reply_turn 并发语义不对称

- Severity: Medium
- Confidence: High
- Category: Stability
- Status: Confirmed
- Affected area: api/db/session_db.py（语音收口 vs 文本回复并发写）
- Evidence:
  - File: api/db/session_db.py:254-297（save_reply_turn：IntegrityError 后新事务重读 max(position) 重试一次，再冲突抛 InvalidStateError）对比 :299-347（finalize_voice_session：同窗口读 max+1 追加，无任何 IntegrityError 捕获/重试）
  - Function / Module: `finalize_voice_session` / `save_reply_turn`
  - Relevant behavior: 两条路径共享同一竞态窗口（读 max → 写），唯一约束兜底都会拒绝重复 position，但只有文本轮路径处理了冲突；语音收口冲突时原始 IntegrityError 直接冒泡到全局异常处理器渲染 500（信封 1005）。
  - Changed functions: 两者均为本范围新增/重写（a460f5e）
  - Related unchanged code: api/modules/session_engine/agent.py:801-810 调用 finalize；文本回复与语音会话可同时活跃（文本 reply 不检查 voice fact 状态）
- Change type: Modified
- Problem: 同一竞态窗口（读 max position → 写）的两条写路径，一条有 IntegrityError 捕获加重试，另一条没有；语音收口冲突时原始异常直接冒泡成 500。
- Why it matters: 修复 F7 的重试语义只覆盖了文本轮；F8 的 append-only 改造引入了新的并发写路径但未继承同款防护，形成"同类问题两种处置"的不一致。
- Realistic failure scenario: 用户开着语音会话的同时在另一标签页发文字消息（或双端登录），文本轮恰在语音收口的读-写窗口内落库，收口撞唯一约束 → voice/complete 返回 500；用户重试虽会成功（重读 max），但体验是偶发不可复现的报错，且该轮档案更新被跳过。
- User-visible impact: 偶发 500 + 复盘/反馈延迟到重试之后；无数据损坏（约束保住了完整性）。
- Minimal fix: 把 save_reply_turn 的两段重试循环提取为共享辅助（或直接在 finalize_voice_session 复制同款 for attempt in range(2) 结构），冲突时记 warning 重试一次。
- Better long-term fix: 仓储层统一"position 分配写路径"入口，两条路径共用同一冲突策略，防第三次新增写路径时再漂移。
- Regression test suggestion: tests/db/test_session_write_integrity.py 复用 `_read_max_position` 测试缝隙——对 finalize_voice_session 伪造首次过期读值，断言重试后 append 成功（当前该缝隙只服务 reply 路径）。
- Estimated effort: 1 小时

### Finding: 迁移 0011 在存量重复 position 数据上直接失败，无迁移内去重或清晰报错

- Severity: Low
- Confidence: High
- Category: Stability
- Status: Confirmed
- Affected area: api/migrations/versions/20261001_0011_session_message_position_unique.py
- Evidence:
  - File: api/migrations/versions/20261001_0011_session_message_position_unique.py:14-19（batch_alter_table 直接 create_unique_constraint，无前置查重/去重步骤）
  - Function / Module: `upgrade()`
  - Relevant behavior: 修复前的 max+1 并发竞态可能在既有库留下重复 (session_id, position) 行；约束创建在有脏数据的库上直接失败，错误为数据库原始约束冲突信息，不含"哪条数据脏"的指引。
  - Related unchanged code: docs/deployment.md:37-38 已写明人工预检 SQL（GROUP BY/HAVING 查重），属运行手册缓解
- Change type: Added
- Problem: 约束创建迁移未对存量数据做预检或去重，命中脏数据时以数据库原始约束错误中断，不指明哪张表哪些行违规。
- Why it matters: 带脏数据的存量库升级中断在 0011，且报错不指向根因；runbook 的人工预检 SQL 只有读过文档的人才会执行。
- Realistic failure scenario: 曾跑过修复前代码且命中过并发写竞态的库执行 `alembic upgrade head`，在 0011 报 IntegrityError 中断，运维需自行联想到查重 SQL。
- User-visible impact: 升级阻断（fail-closed，无静默损坏）；修复成本是一次人工查重。
- Minimal fix: 在 0011 的 upgrade 开头加显式预检（SELECT 重复分组，命中即 raise 带查重 SQL 的清晰错误），或直接去重（保留每组最小 created_at 行后重建）。
- Better long-term fix: 把"约束类迁移必须自带脏数据预检/清理"写入迁移规范（repo 已有 pg_migration_roundtrip，可加一条带脏数据的往返变体）。
- Regression test suggestion: tests/db/test_session_write_integrity.py 新增 sqlite_only 用例——先插入重复行再跑 0011，断言得到指向性错误信息（或去重后成功）。
- Estimated effort: 30-60 分钟

### Finding: compose 自称"可运行的最小拓扑"但开箱必失败，与生产门控冲突

- Severity: Low
- Confidence: High
- Category: Release
- Status: Confirmed
- Affected area: infra/docker/docker-compose.yml + docs/deployment.md
- Evidence:
  - File: infra/docker/docker-compose.yml:1-3（注释"是可运行的最小拓扑"）、:26-45 与 :47-63（api/worker 的 environment 仅 APP_ENV/DATABASE_URL/REDIS_URL/AUTH_JWT_SECRET 四项）
  - Function / Module: `Settings.validate_runtime()`（api/core/config.py:195-248 要求 ALLOWED_ORIGINS、FRONTEND_PUBLIC_BASE_URL、AUTH_COOKIE_SECURE、MODEL_RUNTIME_MODE=live、R2 三项、SMTP 四项、Deepgram 三项等）
  - Relevant behavior: APP_ENV=production 触发完整门控，compose 未提供其余必填项也没有 env_file 引用——`docker compose up` 后 api 与 worker 必然 ConfigurationError 退出（fail-closed，报错会逐项点名）；deployment.md 第 2 节列出键清单但未说明如何注入 compose。
- Change type: Added
- Problem: 编排文件给 api/worker 声明 APP_ENV=production 却只注入 3 个必填变量，也没有 env_file 引用，与 17 项启动门控直接冲突；文档列出键清单但不说明注入方式。
- Why it matters: 首次部署体验是"照文档跑起来即崩溃"，报错虽诚实但入口文档与编排文件互相踢皮球，且与文件自称"可运行的最小拓扑"矛盾。
- Realistic failure scenario: 新用户按 README → compose up → api/worker 双双 crashloop，需要自行领悟"把 17 项手工补进 compose 的 environment 或另建 env 文件"。
- User-visible impact: 部署首次成功率低；无安全风险（门控正确拦截）。
- Minimal fix: compose 的 api/worker 加 `env_file: - .env.production`（文件不存在时给出明确指引的文档段落），deployment.md 第 2 节补一行注入方式；或把注释改为"需先补齐 env 才可运行"。
- Better long-term fix: 提供 `.env.production.example` 完整模板（.env.example 已有键位，缺一个生产态示例），compose 引用之。
- Regression test suggestion: CI docker job 加一步 `docker compose config`（至少校验编排语法与变量引用闭合）；文档一致性可在 feature 验收清单中固定。
- Estimated effort: 30 分钟

### Finding: Dockerfile 以 root 运行且基础镜像仅 tag pin

- Severity: Low
- Confidence: High
- Category: Security
- Status: Confirmed
- Affected area: infra/docker/Dockerfile
- Evidence:
  - File: infra/docker/Dockerfile:4（`FROM python:3.12-slim`，未 pin digest）、全文件无 `USER` 指令（uvicorn 以 root 跑，绑 8000 端口无需特权）
  - Function / Module: 镜像定义整体
  - Relevant behavior: 容器内进程持 root 权限；基础镜像 tag 可变（同 tag 内容可漂移）；uv 版本已 pin（0.9.3，好）。
- Change type: Added
- Problem: 镜像缺少 USER 指令（uvicorn 以 root 运行），基础镜像用可变 tag 而非 digest pin；uv 版本已 pin 但两层加固面均缺。
- Why it matters: 容器逃逸/供应链场景下的标准加固面缺失；个人项目现实风险低，但与镜像可复现目标（注释自称"可复现"）不完全一致。
- Realistic failure scenario: 应用层 RCE（如未来某个反序列化漏洞）→ 攻击者直接持容器 root；基础镜像被上游变更引入破坏性更新时构建不可复现。
- User-visible impact: 无直接用户可见影响；属纵深防御缺口。
- Minimal fix: Dockerfile 增加 `RUN useradd -r app && chown -R app /app` + `USER app`（EXPOSE 8000 非特权端口，改动零风险）；基础镜像按 digest pin 或至少固定 minor。
- Better long-term fix: 接入镜像扫描（trivy/grype）进 CI docker job，与 build 并列。
- Regression test suggestion: CI docker job 增加 `docker inspect --format '{{.Config.User}}'` 断言非空（或以 hadolint 规则固化）。
- Estimated effort: 30 分钟

### Finding: think 上游配置不在启动期 fail-closed 门控内，缺配只在中通电话时 500

- Severity: Low
- Confidence: High
- Category: Release
- Status: Confirmed
- Affected area: api/core/config.py 生产门控 vs api/integrations/deepgram/voice_agent.py 请求期校验
- Evidence:
  - File: api/core/config.py:240-245（生产门控语音段只查 DEEPGRAM_API_KEY / DEEPGRAM_AGENT_BASE_URL / DEEPGRAM_AGENT_THINK_MODEL）对比 api/integrations/deepgram/voice_agent.py:151-158（`validate_deepgram_think_upstream_settings` 查 UPSTREAM_BASE_URL/API_KEY，但在 api/routes/v1/deepgram.py:85-93 以每请求 500 configuration_error 的形态暴露）
  - Function / Module: `Settings.validate_runtime()` / `validate_deepgram_think_upstream_settings()`
  - Relevant behavior: 门控反转批次（d6fb4e0）的清单没有覆盖 think 代理依赖的三个键（UPSTREAM_BASE_URL / UPSTREAM_API_KEY / PROXY_PUBLIC_BASE_URL）；代理路径配置不全时系统正常启动，直到第一个语音会话的 think 回源才拿到 500。
- Change type: Added
- Problem: 生产门控语音段与请求期校验器覆盖的键集不一致：THINK_MODEL 进了启动清单，而代理路径必需的 UPSTREAM_BASE_URL/API_KEY 只在请求期校验。
- Why it matters: fail-closed 门控的覆盖缺口——"带病上线"形态从进程级缩小到功能级，但仍是启动后才暴露，且暴露点在用户可感知的语音会话中。
- Realistic failure scenario: 生产部署漏配 DEEPGRAM_AGENT_THINK_UPSTREAM_API_KEY，健康检查全绿、语音 bootstrap 成功（bootstrap 只查 PROXY_PUBLIC_BASE_URL 决定是否签发 think endpoint，未校验上游），首通语音的 think 环节 500，Deepgram 侧表现为助手"卡住"。
- User-visible impact: 语音链路部分降级且定位成本高（服务端日志才有原因）。
- Minimal fix: 生产门控语音段补一条联动校验——DEEPGRAM_AGENT_THINK_MODEL 已配时，若 DEEPGRAM_AGENT_THINK_PROXY_PUBLIC_BASE_URL 非空则要求 UPSTREAM_BASE_URL/API_KEY 同配。
- Better long-term fix: 把"门控键与其依赖键做存在性联动"作为 Settings 校验的通用模式，避免逐项点名的清单继续漂移。
- Regression test suggestion: tests/core/test_config.py 新增用例——production + THINK_MODEL + PROXY_PUBLIC_BASE_URL 配置但缺 UPSTREAM_API_KEY 时断言 ConfigurationError 点名该键。
- Estimated effort: 30 分钟

### Finding: Redis 故障降级时限流算法静默变化（固定窗口 → 滑动窗口 + 进程级）

- Severity: Info
- Confidence: High
- Category: Stability
- Status: Confirmed
- Affected area: api/services/llm_rate_limit.py / auth_rate_limit.py 的降级路径
- Evidence:
  - File: api/services/llm_rate_limit.py:135-146（Redis 路径：固定窗口，键含窗口序号）对比 :86-109（降级路径 InMemoryLLMRateLimiter：滑动窗口时间戳队列）；:126-128 注释仅声明"护栏不应成为单点故障"
  - Function / Module: `RedisLLMRateLimiter.consume` 的 except RedisError 分支
  - Relevant behavior: Redis 抖动期间同一 (action, key) 的限流语义从"跨进程固定窗口"静默变为"进程内滑动窗口"——多实例部署下配额按实例数倍增，恢复后窗口边界又不同；无 metric/告警标记降级态（仅 warning 日志）。
- Change type: Added
- Problem: Redis 路径与降级路径实现了两种不同的限流算法（固定窗口 vs 滑动窗口），且作用域从跨进程退化为进程级，切换时无任何显式信号。
- Why it matters: 降级语义漂移未被显式建模，监控若只看错误率会漏掉"限流已半失效"的中间态；多实例部署下退化窗口的配额放大不可事后审计。
- Realistic failure scenario: Redis 滚动重启 2 分钟，期间匿名滥用者获得 N 倍配额窗口，事后无聚合信号可查。
- Minimal fix: 降级路径在日志之外补一个可观测标记（如 span 属性 / 计数器日志键 `rate_limit_degraded=true` 汇总），并在 quality-guidelines 注明这是已接受取舍。
- Better long-term fix: 降级时保持固定窗口算法（进程内也可按窗口分桶），消除算法漂移。
- Regression test suggestion: 现有 FlakyRedis 测试追加断言降级路径的日志/标记键（低成本）。
- Estimated effort: 1 小时

### Finding: 写完整性并发测试为 seam 模拟而非真实并发

- Severity: Info
- Confidence: High
- Category: Testing
- Status: Confirmed
- Affected area: tests/db/test_session_write_integrity.py
- Evidence:
  - File: tests/db/test_session_write_integrity.py:135-145（monkeypatch `_read_max_position` 伪造过期读值模拟并发窗口）、:173-199（always-stale 读值模拟持续冲突）
  - Function / Module: `test_save_reply_turn_retries_once_after_position_conflict` 等
  - Relevant behavior: docstring 诚实声明"无需真实并发即可稳定复现唯一约束冲突"；唯一约束本身有 DB 层直测（:97-122），但"两个真实协程同时 save_reply_turn/finalize"从未被任何一个测试执行过——Finding 3 的 finalize 不对称正是这类测试能抓住的形态。
- Change type: Added
- Problem: 并发窗口用 monkeypatch 伪造过期读值复现，两个真实协程同时写同一会话的场景没有任何测试执行过。
- Why it matters: 并发正确性依赖推理与 seam 复现，而非对真实交错行为的断言；Finding 3 的 finalize 不对称正是这类测试能抓住的形态。
- Realistic failure scenario: 未来某次重构改变了事务边界（如把 flush 提前），seam 测试依旧全绿，真实并发下才暴露。
- Minimal fix: 不强求——补一条 `asyncio.gather` 双任务同会话写回复 + 断言一方 InvalidStateError/一方成功的真实并发用例（SQLite 下仍确定性可断言约束行为）。
- Better long-term fix: CI backend-postgres job 中把真实并发写用例跑在真 PG 上（行锁/死锁语义与 SQLite 不同，正是平价 job 的价值所在）。
- Regression test suggestion: 见上。
- Estimated effort: 2 小时

## 5. Security Concerns / 安全分析

- Coverage: High
- Inspected evidence: api/core/security.py、api/common/middleware.py、api/common/deps.py、api/core/config.py、api/services/auth_rate_limit.py、llm_rate_limit.py、rate_limit_window.py、api/routes/v1/deepgram.py、api/integrations/deepgram/voice_agent.py、api/routes/v1/sessions.py、api/services/media_service.py、api/modules/session_engine/{service,agent}.py 全读；六条不变量逐条对照
- Exclusions / limits: 未做渗透测试；未跑依赖 CVE 扫描；反代层（uvicorn --proxy-headers）未实测

**已验证成立的不变量（修复批次主体，正面确认）**

1. **server-attested identity**：`get_resource_owner` 对访客 Cookie 先 `verify_signed_value`（HMAC-SHA256 + `hmac.compare_digest` + rpartition 拆分，api/core/security.py:136-152），失败一律当"无身份"重签，伪造值到不了 owner_id/限流键/存储路径（api/common/deps.py:66-77）；IP 兜底键只取 `request.client.host`，显式拒绝 XFF（llm_rate_limit.py:206-229）。
2. **bounded bodies**：`BodySizeLimitMiddleware` 纯 ASGI 双路径（声明 Content-Length 直接拒；chunked 逐块计数超限先 413 再断，哨兵异常不外逃），12MB 门兜底全部 http body；上传走 64KB 分块 `_validate_and_measure`，魔法字节首 12 字节判定，无一处整包读入（media_service.py:117-141）。
3. **bearer 令牌生命周期契约**：think 令牌带 `gen` claim（bool 显式排除），代理校验链四段 fail-closed（缺 claim / 无 fact / 非 active / 代数落后 → 统一 401 "Proxy authorization required"，原因只进服务端日志，deepgram.py:146-177）；0016 的 server_default=0 与"无活跃绑定"语义自洽；voice/complete 保留代数不清零（agent.py:766-771），re-bootstrap +1 令旧令牌失效。
4. **fail-closed env gate**：NON_PRODUCTION_ENVS 白名单外一切取值（含空串/拼写错误）执行 17 项清单（config.py:195-248）；REDIS_URL 缺失在多 worker 场景的危害写进报错文案。
5. **展示名防泄漏**：LLM display names 逐字段判定（空/超长/raw-id 变体泄漏 → 确定性回退 + warning，review_builder.py:243-279），评测台与生产共享 `identifier_variants` 单一事实源。

**残余风险**：见 Finding 6（root 容器）、Finding 7（think 上游配置门控缺口）、Finding 2（限流 Lua 零执行覆盖——控制本身在，但其最底层实现未被测过）。

## 6. Stability Concerns / 稳定性分析

- Coverage: High
- Inspected evidence: session_db.py 全读、session_engine/agent.py 全读、migrations 0011-0016、llm_usage_db.py、review_summarizer.py、main.py（/readyz）、反馈降级链
- Exclusions / limits: 未做故障注入；Redis 降级/恢复的实测依赖真 Redis

**已验证成立**：orchestration failure policy 三处增强分支（反馈、复盘、档案）全部"只捕获 Exception、CancelledError 上抛、degraded=true 日志、单一转换点 `_degraded_feedback_with_log`"（agent.py:443-446、:526-562、:264-300）；教练分支失败取消反馈任务并保持取消语义（agent.py:429-434）；position 唯一约束 + reply 路径两段重试；语音收口 append-only 且事件监听测试证明无 delete（test_session_write_integrity.py:225-284）；usage sink fire-and-forget 且 ContextVar 调用线程捕获（llm_usage_db.py:80-102）；/readyz 探针带 2s 硬超时、down 才 503。

**残余风险**：Finding 3（finalize 并发不对称）、Finding 4（0011 脏数据）、Finding 8（降级算法漂移）。

## 7. Performance Concerns / 性能分析

- Coverage: Medium
- Inspected evidence: max_tokens 全接线核验（coach 300/feedback 400/scene 500/review 300，openai.py payload builder + vision_provider.py:97）、教练输出 2000 字符硬顶、复盘 5s 有界等待、上传线程池分块、限流字典 LRU、usage 写线程池化
- Exclusions / limits: 无压测数据；OTel 开启态开销未测；redis 探针每请求新建客户端（/readyz 频率低，可接受）

正面确认：输出预算从"无上限"变为四级独立配额；复盘分支对主价值路径的最大拖累被 `llm_review_wait_seconds=5` 封顶；`asyncio.gather(return_exceptions=True)` 保住一侧失败不取消另一侧已计费调用。无新增性能风险。

## 8. Testing Gaps / 测试分析

- Coverage: High
- Inspected evidence: 全量套件实测（649 passed / 9 skipped / 覆盖率 90.47%，门禁 87）、conftest.py、tests/support/{dialect,engine}.py、test_session_write_integrity.py、test_auth_rate_limit.py、test_coach_evaluation.py、test_review_engine_live.py（skip 语义）、test_dialect_hygiene.py、tests/tools/test_pg_migration_roundtrip.py
- Exclusions / limits: live 评测未实跑（真实 LLM 费用）；前端 41 个变更文件抽查而非逐文件

**真实性结论（对照"评测台、方言参数化、守卫测试是否给了虚假信心"的复审重点）**：
- **评测台不是 tautology**：硬规则（CJK/长度/追问/meta 泄漏/复读，含边界）是确定性 always-on 断言进 CI；LLM judge 是 `RUN_COACH_EVAL=1` 门控的本地 live 工具，judge 故障有兜底（final_pass 回落 hard_pass）；review 评测纯硬规则不接 judge。fixture 契约校验（数量/矩阵/mock 前提）锁定。
- **方言层是真实平价而非标签**：`ECHOWHALE_TEST_DATABASE_URL` 显式开关、`sqlite_only` 必须写理由、PG 共享库每用例 drop metadata（alembic_version 除外）、Windows Selector loop 处理有理有据；CI backend-postgres job 在真 PG 上跑迁移链 + 全套测试 + 含种子数据的 downgrade 往返。
- **守卫测试有效但有边界**：dialect_hygiene 静态扫描 + 逐条理由的 allowlist（已知 P2 绕过面不重复报告）；live 测试 skip 语义诚实（显式 env + 成本警告）。
- **虚假信心点**：Finding 2（Lua 假执行）与 Finding 9（并发 seam 模拟）是仅有的两处"绿色不等于验证过"。

## 9. Maintainability Concerns / 可维护性分析

- Coverage: High
- Inspected evidence: 死代码 rg 断链验证（session_prompts/session_summary/mockApi/前端 8 个删除组件均无残留引用；TurnFeedbackCard 是在用组件非残留）、review_builder.py 单源机制、learner_profile.py 注入面常数、docs/api.md 抽查、AGENTS/quality-guidelines 更新
- Exclusions / limits: 前端剩余页面未逐行精读

正面确认：F17/F19/F21 的清理真正完成（-1057 行单提交）；场景文案/错误类别展示名/CEFR 标签全部服务端单源，前端零副本；`agent.py` 的并发取舍（档案 last-write-wins）与 `middleware.py` 的 413 无 request-id 取舍都以注释成文——"决策留痕"的密度显著高于上轮。新增债务仅一处已声明项：`security.py:129-130` 注明 cursor 签名 `_sign_cursor_payload` 与 `sign_value` 同构未合并（后续收敛点）。

## 10. Design / 设计原则分析

- Coverage: High
- Inspected evidence: 六不变量对照 spec 原文、新模块 Protocol+factory 抽查（learner_profile_db/llm_usage_db/rate_limit_window/telemetry）、测试缝隙设计、归因 ContextVar 的 yield 依赖论证（deps.py:80-95，含"同步依赖进线程池丢 ContextVar"的正确分析）
- Exclusions / limits: —

正面确认：本轮最突出的设计质量是**"增强分支与主价值分离"被一致执行**——复盘降级回模板、档案写失败不影响已提交回复轮、display name 解析失败回退确定性文案，全部不整轮失败。fail-fast 与 fail-closed 的分工清晰（配置在 import 期、身份在依赖层、生命周期在校验链）。SRP 上唯一的重载点是 `session_engine/agent.py`（990 行，编排 + 语音 + 档案 + 游标），但职责边界仍清晰，不构成结构性风险。

## 11. Release Concerns / 发布与交付分析

- Coverage: Medium
- Inspected evidence: ci.yml 全读（PG 平价 job 含迁移链真跑 + downgrade 往返、docker build-only job、eslint+typecheck+coverage 前端 job、权限最小化与并发控制保持）、Dockerfile/compose/.dockerignore、pyproject（fail_under=87，排除项干净）、docs/deployment.md 对照
- Exclusions / limits: 两个新 CI job 首跑未实测（已知暂缓项）；未真实部署

正面确认：requirements.txt 删除后引用残留为零（仅历史性提及）；前端 build 接入 `tsc --noEmit`，eslint exhaustive-deps 升为 error 且豁免逐条写理由；CI 保持 `permissions: contents: read` 与并发取消；uv 0.9.3 pin + `--frozen --no-dev` 层缓存策略正确。残余：Finding 5（compose 开箱必失败）、Finding 6（root 容器）、Finding 1（往返工具护栏）。

## 12. Principles Compliance / 原则遵循汇总

### Principles Violated

| Principle | Violations | Severity | Affected Areas |
|-----------|------------|----------|----------------|
| Fail-Fast（配置类） | 1 | Low | think 上游配置延迟到请求期报错（Finding 7） |
| DRY（安全原语） | 1 | Info | sign_value 与 _sign_cursor_payload 双实现（已声明收敛点） |
| 并发处理一致性 | 1 | Medium | 两条 position 写路径冲突策略不对称（Finding 3） |

### Principles Respected

- **Protocol + factory + fake**：全部新外部依赖（限流窗口、usage sink、档案仓储、OTel exporter 测试注入口）按既有纪律落地，测试零网络。
- **单一事实源**：场景文案、错误类别 label、CEFR 集合、identifier 变体规则、ReviewCopy 字段上限（生产/评测同表）收敛彻底。
- **决策留痕**：并发取舍、中间件顺序盲区、测试缝隙、方言差异热点全部注释成文，且沉淀进 quality-guidelines.md 的 spec 级不变量。
- **最小 diff 原则**：0004 迁移的 batch_alter_table 改造、mock 反馈的逐字节兼容承诺，显示对存量行为契约的尊重。

---

## 13. Recommended Fix Order

### Fix Immediately（下一个任务队列的第一批）

1. pg_migration_roundtrip 加程序化确认门（Finding 1，30 分钟）——本机 .env 即命中风险场景。
2. finalize_voice_session 补唯一约束冲突重试（Finding 3，1 小时）。

### Fix Before Stable Release

3. 限流 Lua 真 Redis 集成测试（Finding 2，1-2 小时）。
4. think 上游配置纳入启动门控联动校验（Finding 7，30 分钟）。
5. compose env_file 化 + deployment.md 注入说明（Finding 5，30 分钟）。
6. Dockerfile 非 root 用户 + 基础镜像 digest pin（Finding 6，30 分钟）。
7. 迁移 0011 预检/去重（Finding 4，30-60 分钟；有存量数据的库升级前必做）。

### Schedule Later

8. 限流降级态可观测标记（Finding 8）。
9. 真实并发写测试进 PG job（Finding 9）。
10. sign_value / _sign_cursor_payload 收敛（代码内已声明）。
11. 上轮遗留：F9 历史列表 INNER JOIN reviews、F16 数据保留/账号删除路径、F21 useDeepgramVoiceAgent 668 行拆分。

### Ignore for Now

- BodySizeLimit 流式超限后下游并发响应的理论竞态（客户端拿 413 优先的既有权衡）。
- /readyz 每请求新建 Redis 客户端（探针频率低）。
- http.target 原始 path 进 span 属性（OTel 惯例，span 名已用低基数模板）。

## 14. Quick Wins

| 修复 | 收益 | 工作量 |
|------|------|--------|
| pg_roundtrip 确认门（Finding 1） | 消除清库脚枪 | 30 分钟 |
| finalize 重试（Finding 3） | 消除偶发 500 | 1 小时 |
| think 配置联动校验（Finding 7） | 配置错误启动期暴露 | 30 分钟 |
| compose env_file + 文档一行（Finding 5） | 首次部署可走通 | 30 分钟 |
| Dockerfile USER 指令（Finding 6） | 关闭 root 面 | 30 分钟 |

## 15. Approval Recommendation

**Approve with comments**（带评论通过）。无 Critical/High 发现；23 个提交的修复方向、实现质量与测试配套均属上乘，三条 Medium 建议作为下一个任务队列处理，不构成回滚或阻断理由。CI 两个新 job 的首跑验证（已知暂缓项）应在下次 push 时补上实测记录。

## 16. 收官对比（vs 2026-10-01 全量审计）

| 维度 | 2026-10-01 | 2026-10-07 回访 | 变化 | 依据（增量范围证据） |
|------|-----------|----------------|------|---------------------|
| Security | 5.5 B | 8.5 A | +3.0 | 上轮三扇"真正能被打的门"（Cookie 轮换/上传内存/配置门控）全部关闭且经六不变量逐条验证；IDOR、语音滥用面（bootstrap 限流 + think 生命周期）关闭。残余为加固面而非敞开的门 |
| Stability | 6.5 B | 8.0 A | +1.5 | 分支失败语义反转（反馈/复盘/档案降级）、并发写双保险（约束+重试）、语音收口 append-only、/readyz。残余为 finalize 不对称与 0011 脏数据两个局部点 |
| Performance | 7.0 A | 8.0 A | +1.0 | 成本从"不可知不可控"变为"四级 max_tokens + usage 账本 + 归因列"；复盘拖累 5s 封顶。未给满分：无压测数据、OTel 开销未测 |
| Testing | 7.0 A | 8.5 A | +1.5 | 224→649 测试、后端覆盖率门禁（实测 90.47%）、真 PG 平价 job + 迁移往返进 CI、评测台硬规则 always-on。未给满分：Lua 假执行与并发 seam 两处真实性缺口 |
| Maintainability | 7.5 A | 8.5 A | +1.0 | 死代码清零、文案/集合/上限全面单源、方言层收敛、决策注释密度高、spec 不变量沉淀 |
| Design | 7.0 A | 8.5 A | +1.5 | "增强分支不绑架主价值"成为全仓一致模式；Protocol+factory 零破例；测试缝隙刻意设计 |
| Release | 5.0 B | 7.5 A | +2.5 | Dockerfile/compose/runbook/迁移往返/PG 平价/eslint/覆盖率门禁从无到有。未回 8+：compose 开箱即败、root 容器、registry 推送与两 job 首跑未实测 |
| **Overall** | **6.5 B** | **8.2 A** | **+1.7** | 传输层问题批次化关闭后，质量重心已按上轮建议成功转向"教学大脑"（提示词工程/LLM 复盘/学员档案/评测台）与交付完整性 |

**上轮 21 条发现处置对账**：已修复/处置 18 条（F1-F8、F10-F15、F17-F20，其中 F5 的 XFF 以"TCP 对端 + --proxy-headers 运行手册"方案关闭，F18 以生产门控 SMTP 四字段关闭）；未动 3 条且均属上轮 Schedule Later 及之后（F9 历史列表 INNER JOIN、F16 数据保留/账号删除、F21 语音 hook 体积）——无回归、无恶化。

**结论**：修复纪元兑现了上轮 Fix Order 的主体承诺，且回访发现的 9 条新问题全部是"第二批次的收尾项"，没有一条否定第一批次的工作。下一任务队列以第 13 节 Fix Immediately 两项起步即可。

---

*报告遵循 skill 模板生成；所有发现均有 file:line 级证据；覆盖率限制已在 Coverage Matrix 注明；未修改任何被审计文件。生成后元数据已存档至 .claude/audits/。*
