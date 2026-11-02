# Feature: `llm_resilience_guardrails`

## 基本信息

- `feature`: `llm_resilience_guardrails`
- `module`: `platform_foundation`（LLM 共享底座）
- `status`: `feature_test_passed`
- `updated_at`: `2026-09-30`

## 目标

给三条 LLM 链路（scene / coach / feedback）补上统一的韧性层与用量护栏：主备 failover、瞬时错误重试、请求级 deadline、统一 JSON 解析、usage 计量、LLM 路径限流，并清理一批 async 迁移遗留的生产 bug。

## 韧性层（api/integrations/llm/resilience.py）

- `LLMAttempt(name, call)` + `run_llm_with_failover(...)` 统一原先三种各写一法的 failover 语义
- 错误分类：`ModelProviderError` / httpx 超时与传输错误 / 解析类 `ValueError` 视为可重试；`ConfigurationError` 直接上抛
- 同一 provider 先带退避重试 `LLM_MAX_RETRIES_PER_PROVIDER` 次再切换主备
- `LLM_REQUEST_DEADLINE_SECONDS`（默认 45s）限制整条调用链总预算，消除"主 30s + 备 30s 才报错"的最坏情况
- 每次 attempt 失败记 WARNING 日志（provider 名 + 异常 + 耗时），feedback 引擎原先静默吞掉 pydantic 校验错误的问题一并解决
- scene 引擎通过 `compose_failure` 保留原有错误归并语义（全部 provider 判定图片不可用时仍返回 `UnsupportedSceneImageError`）

## 统一 JSON 解析（api/integrations/llm/json_utils.py）

- 三份 `_load_json` 拷贝收敛为 `parse_llm_json`
- 修复 `strip("`")` 会剥掉字符串内所有反引号的 bug，改为只剥 Markdown 围栏与语言标签
- 模型输出解析/校验失败按可重试的 provider 错误处理，触发重试与 failover

## 用量计量（api/integrations/llm/openai.py）

- 响应中的 `usage` 字段不再丢弃：默认结构化 INFO 日志（model / prompt / completion / total tokens）
- 客户端支持注入 `usage_recorder`，后续接成本看板不需要再改协议层

## LLM 路径限流（api/services/llm_rate_limit.py）

- `POST /sessions`（session_start）与 `POST /sessions/{id}/reply`（reply）按 owner 限流，匿名 visitor 身份同样覆盖
- 有 `REDIS_URL` 走 Redis 固定窗口（INCR + EXPIRE），跨 worker 共享；Redis 为空时退化为进程内滑窗
- **Redis 故障自动降级**为进程内计数并记 WARNING——护栏不成为主路径的单点故障
- 超限抛既有 `TooManyRequestsError`（429 / code 1006 统一信封）
- 默认规则：session_start 10 次/小时、reply 30 次/小时，均可经 settings 覆盖

## 会话编排修复（api/modules/session_engine/agent.py）

- `asyncio.gather(..., return_exceptions=True)`：一侧 LLM 失败不再取消另一侧已在计费的调用；双方都跑完后统一上抛业务异常
- `assert` 输入校验改为显式 `AppValidationError`（原实现在 `python -O` 下消失）
- 历史分页 cursor 加 HMAC 签名（密钥取 `AUTH_JWT_SECRET`），伪造或旧版无签名 cursor 一律 400

## 存量生产 bug 修复（本轮顺带发现，均为 async 迁移遗留）

- `api/db/session_db.py`：5 处 `await db_session.scalars(...).all()` 运算符优先级错误（在协程上取 `.all()`），`list_user_sessions` / 历史分页 / 批量 review / 消息分页 / 事件列表原本全部运行时崩溃
- `api/db/media_db.py`：`save_media` 同时 `add` + `merge` 导致同一记录双写触发唯一约束，改为仅 `merge` upsert
- `api/modules/scene_engine/evaluation.py`：`asyncio.to_thread` 包 async 服务导致协程从未执行，评测 harness 直接 `AttributeError`，改为直接 `await`
- `.env.example`：`MODEL_RUNTIME_MODE` 从 `live`（空配置必启动失败）改回 `mock` 并附迁移说明

## 测试与验证

- 全量 `uv run pytest tests`：**188 passed, 2 skipped**（修复前基线 116 passed / 40 failed）
- 修复的 40 个存量失败均为 async 迁移后未同步的旧测试（fake service/仓储同步签名、同步 sqlite fixture）；db 层改用 aiosqlite + anyio
- 新增：`tests/integrations/test_llm_resilience.py`（重试/failover/deadline/分类/日志）、`test_llm_json_utils.py`、`test_llm_usage.py`、`tests/services/test_llm_rate_limit.py`（含 Redis 故障降级）、`tests/modules/test_history_cursor.py`
- session 路由新增 429 信封集成用例
- mock 模式冒烟（TestClient + aiosqlite）：start 200 → reply 200（grammar / more_natural / useful_words 齐全）→ 连续超限 429/1006

## 配置项

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LLM_REQUEST_DEADLINE_SECONDS` | 45 | 单次请求内 LLM 调用链总预算 |
| `LLM_MAX_RETRIES_PER_PROVIDER` | 1 | 同一 provider 瞬时错误重试次数 |
| `LLM_RETRY_BACKOFF_SECONDS` | 0.5 | 重试退避基数（线性） |
| `LLM_SESSION_START_LIMIT` | 10 | session_start 每窗口上限 |
| `LLM_SESSION_START_WINDOW_SECONDS` | 3600 | session_start 窗口 |
| `LLM_REPLY_LIMIT` | 30 | reply 每窗口上限 |
| `LLM_REPLY_WINDOW_SECONDS` | 3600 | reply 窗口 |

## 遗留与后续批次

- 架构收敛（第二批）：三套 provider 脚手架合并为共享 agent runtime、`response_format` JSON mode、coach 上下文滚动摘要（兑现 PRD v0.4 会话总结）、DB 读放大与 N+1、auth 链路迁 async
- 体验升级（第三批）：文字回复 SSE 流式（前端文字路径尚未接线，需先定产品形态）、场景分析按 media_id 缓存并经 RQ 异步化
