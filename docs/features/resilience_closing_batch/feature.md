# 后端韧性收尾批次（resilience_closing_batch）

> 审计报告（audit-report-EchoWhale-2026-10-01.md）的尾部小遗留收口，六个独立小项：
> 语音收口降级对齐、用量归因、限流原子化、agent_ops bootstrap 修复、AGENTS.md 读取
> 顺序断裂处置、telemetry e2e mock pin。全部为韧性与工具一致性修复，API 契约与前端
> 零改动。
> Trellis 任务：`.trellis/tasks/10-06-resilience-closing-batch`。

## 基本信息

- `feature`: `resilience_closing_batch`
- `status`: `feature_test_passed`
- `branch`: `dev`（审计后续批次按仓内惯例直接落 dev）
- `module`: `platform_foundation`
- `cross_module`: `yes`（R1/R2 涉及 session_orchestration 的会话编排与会话路由）
- `owner`: `lucky`
- `updated_at`: `2026-10-06`
- `merge_target`: `module/platform_foundation`

## 背景

- failure policy 三条链路（reply / stream / voice）中 voice 收口是最后一个缺口：
  反馈失败会把整个语音收口打挂（既有测试锁定该旧语义），与另两条链路的降级语义不一致。
- llm_usage 账本自创建起只记 model/tokens，"谁花的、哪次会话花的"无法回答——
  当年注释"归因归 request-id 批次"，而该批次的 ContextVar 基建早已就位。
- 两个 Redis 限流器 INCR 与首次 EXPIRE 两步执行，进程在两命令间崩溃会留下无 TTL 的
  永久键（窗口永不翻新，配额黑洞）。
- agent_ops bootstrap 连续两个批次报"未映射占位符"被迫手写 feature.md（工具自身缺陷）。
- 根 AGENTS.md 读取顺序引用 gitignore 内不存在的 `.codex/AGENTS.md`，协作者 clone 即断。
- telemetry e2e 只靠门禁命令的环境 pin 保证 mock，裸跑会在 live .env 下打真实 provider。

## 六子项处置表

| # | 子项 | 处置 | 关键文件 |
| --- | --- | --- | --- |
| R1 | 语音收口反馈降级对齐 | `complete_voice_session` 反馈失败走 `_degraded_feedback_with_log` 单一转换点降级占位反馈 + degraded=true 日志，收口照常落库返回；`feedback_degraded=True` 让复盘走既有 None 短路（不起 LLM 汇总）；`except Exception` 保 CancelledError 语义；既有"失败不落库"测试翻转为"降级并落库"。failure policy 三链路对齐 | `api/modules/session_engine/agent.py`、`tests/modules/test_session_engine.py` |
| R2 | usage owner/session 归因 | `request_context.py` 新增 owner/session ContextVar（token set/reset 模式）；`deps.get_attribution_owner` **async** yield 依赖（同步依赖进线程池会丢上下文）接管 sessions 全部路由；reply/voice-complete 在 handler set/finally 复位，**SSE 生成器内部首行** set session（handler 返回后才迭代）；think 代理因 service token 过不了 access-token 校验，改为会话确认后 handler 内 set（`session_head.user_id` 即 owner 形态）；sink `record()` 在调用线程捕获后以参数传线程池（ContextVar 不跨线程）；llm_usage 加可空 owner_id/session_id（迁移 0015 可逆，无索引）；span 补 `echowhale.owner_id` | `api/common/request_context.py`、`api/common/deps.py`、`api/routes/v1/sessions.py`、`api/routes/v1/deepgram.py`、`api/db/llm_usage_db.py`、`api/migrations/versions/20261006_0015_*.py`、`api/common/telemetry.py` |
| R3 | 限流窗口原子化 | 新模块 `FIXED_WINDOW_LUA` + `FixedWindowCounter`（redis-py `register_script`，EVALSHA 优先），两个 Redis 限流器共用；键构造与 RedisError 降级路径不变（server-attested identity 语义不动）；测试 fake Redis 增 `register_script`（按 EVAL 语义模拟），既有共享计数/窗口翻新/降级用例一条未删 | `api/services/rate_limit_window.py`（新）、`api/services/llm_rate_limit.py`、`api/services/auth_rate_limit.py` |
| R4 | agent_ops bootstrap 占位符 | 补映射 `<feature-name>`/`<bug-name>`→slug、`<module-name>`→module 或 platform_foundation、`<YYYY-MM-DD or blank>`→""（published_at 诚实留空）；四子命令（feature\|bug\|module\|version）参数化回归；本文件即由修复后的工具 bootstrap 产出（自证） | `tools/agent_ops.py`、`tests/tools/test_agent_ops.py` |
| R5 | AGENTS.md 读取顺序断裂 | `.codex/` 整体在 .gitignore（local-only），定案**指向真实文档**而非放行入库（避免第二协议源）：读取顺序第 4 项改 `docs/control/agent-governance.md`，硬规则与说明节的 `.codex/` 引用全部清理，状态词/分支约定以 project-index.md 渲染块为准 | `AGENTS.md` |
| R6 | telemetry e2e mock pin | `e2e_client` fixture 增 `monkeypatch.setattr(settings, "model_runtime_mode", "mock")`（仓内既有模式），自建 service 的关闭态用例同样 pin；裸跑（live .env、无环境 pin）4 passed 确定性通过 | `tests/api/test_telemetry_e2e.py` |

## 验收标准

- [x] R1：语音收口降级语义落地并翻转测试；failure policy 三链路一致；
- [x] R2：llm_usage 带归因列（迁移 0015 可逆），span 补 owner；归因缺失 NULL 不抛错；
      流式路径上下文传播有测试（探针断言流末帧 owner=visitor:*/session=路径值）；
- [x] R3：两个 Redis 限流器窗口原子化，既有用例语义不变；
- [x] R4：bootstrap 四子命令回归通过；
- [x] R5：读取顺序断裂处置完成；
- [x] R6：telemetry e2e 裸跑确定性通过；
- [x] 全量门禁绿（基线只升不降）+ agent_ops 一致 + 单提交。

## 测试记录

- `feature_test_passed` 的证据（2026-10-06，MODEL_RUNTIME_MODE=mock 进程 pin）：
  - `uv run pytest tests --cov=api`：**635 passed / 9 skipped**（基线 622/9，净增 13），
    覆盖率 **89.56%**（基线 89.42%，门禁 87）；
  - 新增关键用例：语音收口降级落库翻转、request_context set/get/reset、
    sink 归因（同步/异步/NULL 三态）、span owner 属性、**SSE 流末帧归因传播**、
    迁移 0015 可逆、限流 fake 经 script 路径、bootstrap 四子命令参数化回归；
  - `uv run ruff check api tests tools` 全绿；`uv run black --check api tests tools`
    195 文件不变；
  - frontend：`npm run typecheck` 通过、`npm run coverage` 16 文件 115 passed
    （与基线一致），`git status` 证明前端零改动；
  - `uv run python -m tools.agent_ops render` + `check` 一致。
- 主要测试命令：见上；R6 专项：不带环境 pin 裸跑 `uv run pytest tests/api/test_telemetry_e2e.py`。
- 已知缺口：见下节遗留与排除项。

## 设计要点（关键定案摘录）

- 归因是旁路不是业务依赖：无上下文（启动期/后台任务/session_start 创建前的 LLM 调用）
  记 NULL 不报错；session 归因 NULL 为设计预期，非缺陷。
- yield 依赖的 teardown 在响应体（含流式）发送完成后执行，是流式归因不被过早擦除的前提
  （有测试锁定）；同步 yield 依赖会被 FastAPI 挪进线程池，必须 async。
- Lua 脚本只合并 INCR+首次 EXPIRE，键构造留在各限流器；测试 fake 模拟 EVAL 语义契约
  而非 Lua 本身（不引入 fakeredis/lupa 依赖）。

## 遗留与排除项（本批次明确不做）

- think 一次性票据（设计量大，独立立项）；
- CI 加 PG service 容器、前端 eslint 批次（交付门禁批次）；
- registry 推送流水线（需外部凭证决策）；
- judge 主观分歧留观察；
- llm_usage 归因列暂不加索引（只写不读，查询需求出现时再补）。

## 控制面同步

- 已更新 `docs/control/agent-control-plane.json`（features 追加本条 + latest_snapshot）。
- 同步后运行：`uv run python -m tools.agent_ops render` ✓
- 校验：`uv run python -m tools.agent_ops check` ✓

## 合并与关闭

- 本批次按仓内审计后续惯例直接落 dev；`feature_test_passed` 已达成。
- 后续真实联调批次复核归因数据质量（owner/session 非空率）后可写 `closed`。
- 相关文档链接：`.trellis/tasks/10-06-resilience-closing-batch`（prd/design/implement）、
  `docs/features/review_copy_consumption/feature.md`（R4 受害注记的上一批次）。
