# 2026-09-30 LLM 韧性层与用量护栏（第一批架构优化）

## 本轮范围

按"正确性与护栏"批次落地 agent 架构优化第一批，未创建 Trellis 任务（用户未授权），docs 留痕照常执行。

## 生产代码

- 新增 `api/integrations/llm/resilience.py`：`LLMAttempt` + `run_llm_with_failover`，统一原先三种 failover 写法；瞬时错误带退避重试、请求级 deadline（默认 45s）、失败 WARNING 日志
- 新增 `api/integrations/llm/json_utils.py::parse_llm_json`：三份 `_load_json` 收敛，修复 `strip("`")` 误剥字符串内反引号
- coach / feedback / scene 三引擎全部接入韧性层；feedback 不再静默吞 pydantic 校验错误
- `session_engine/agent.py`：`gather(..., return_exceptions=True)` 防止一侧失败取消另一侧计费调用；`assert` 校验改显式异常；历史 cursor 加 HMAC 签名
- `openai.py`：响应 `usage` 计量（可注入 recorder）；删除 `MockOpenAIClient`、no-op `__init_subclass__`、不可达 return 等死代码
- 新增 `api/services/llm_rate_limit.py`：session_start / reply 按 owner 限流，Redis 固定窗口 + 故障降级进程内计数，429 统一信封
- `.env.example`：`MODEL_RUNTIME_MODE` 改回 `mock`（原先 `live` + 空 provider 配置，照抄即启动失败）

## 顺带修复的存量生产 bug（async 迁移遗留）

- `session_db.py` 5 处 `await ...scalars(...).all()` 优先级错误 → 历史列表/分页/批量 review/消息分页/事件列表原为运行时崩溃
- `media_db.py` `add` + `merge` 双写 → 唯一约束冲突，改为仅 merge upsert
- `scene_engine/evaluation.py` `to_thread` 包 async 服务 → 协程从未执行，评测 harness 崩溃

## 测试

- 全量 `uv run pytest tests`：修复前 116 passed / 40 failed → **188 passed / 2 skipped**
- 40 个存量失败全是 async 迁移后未同步的旧测试：fake service/仓储同步签名、同步 sqlite fixture（db 层改 aiosqlite + anyio，新增 dev 依赖 `aiosqlite`）
- 新增韧性层 / JSON 解析 / usage 计量 / 限流（含 Redis 降级）/ cursor 签名 / 429 信封用例
- visitor cookie 上传用例从 `test_auth_routes.py` 移入 `test_media_routes.py`（原先连真实 PG，Windows ProactorEventLoop 下 psycopg 异步不可用）

## 冒烟

mock 模式 + aiosqlite 内存库走真实 HTTP：start 200 → reply 200（feedback 三字段齐全）→ 连续超限 429/1006。

## 遗留

第二批（架构收敛：共享 agent runtime、JSON mode、上下文摘要、DB 读放大、auth 迁 async）与第三批（SSE 流式、场景分析缓存/异步化）待规划。
