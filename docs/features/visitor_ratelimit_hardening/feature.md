# Feature: `visitor_ratelimit_hardening`

## 基本信息

- `feature`: `visitor_ratelimit_hardening`
- `module`: `platform_foundation`（访客身份边界 + 共享限流底座）
- `cross_module`: `yes`（session_orchestration 路由消耗 IP 键；auth 模块的 `auth_rate_limit` 同步有界化）
- `status`: `feature_test_passed`
- `updated_at`: `2026-10-01`

## 目标

修复全量审计报告（`audit-report-EchoWhale-2026-10-01.md`）Finding 1：匿名访客的限流键与资源归属建立在客户端可任意声明的 `echowhale_visitor_id` Cookie 上，可无限轮换绕过 LLM 限流；同时进程内限流字典无界增长。本批次交付服务端可认证的访客身份、有界的限流存储与匿名 IP 维度兜底限流。

## 访客 Cookie 签名化（api/core/security.py + api/common/deps.py）

- 新增通用 `sign_value` / `verify_signed_value`：HMAC-SHA256（密钥复用 `AUTH_JWT_SECRET`）+ `hmac.compare_digest` 恒时比较；`verify_signed_value` 按最后一个 `.` 拆分，任何结构异常/验签失败一律静默返回 None（不抛错）
- `apply_visitor_cookie` 写入 `<visitor_id>.<签名>`；`get_resource_owner` 先验签：签名有效则沿用且不重设 Cookie；缺失/伪造/超长/旧版未签名值一律视为无身份，重新签发全新 visitor_id 并重设 Cookie（fail-closed，不报错打断匿名流程）
- 伪造字符串从此进不了 owner_id、限流键与 R2 存储路径（同时消除任意 key 注入与超长 key 打爆 `String(64)` 列的 500）
- 兼容策略：旧版未签名 Cookie 一律重新签发，匿名访客历史会话失联（可接受的匿名数据丢弃）
- 回滚 = revert 单提交：新签名 Cookie 会被旧代码当 raw id 使用（owner 前缀带签名尾巴，与历史数据失联但不崩溃），回滚窗口短

## 匿名 IP 维度兜底限流（api/routes/v1/sessions.py）

- `start_session` / `reply_to_session` / `stream_reply_to_session` 三个端点：匿名 owner 在 visitor 键之外追加 IP 键消耗（先 visitor 后 IP，任一超限即 429）
- IP 键只取 TCP 对端地址（`request.client.host`），不读 `X-Forwarded-For`——XFF 可被客户端伪造，用它等于把 IP 键也交给攻击者轮换；`request.client` 为 None（部分测试/UDS 部署）时跳过
- 认证用户不受 IP 键影响（`ResourceOwnerContext.is_anonymous` 判定）
- 反代/共享出口 IP 的误伤由放大系数吸收（默认 visitor 限额 ×5）；反代场景如需按真实客户端 IP 计数，需自行评估 `--proxy-headers` 与信任边界的取舍

## 限流存储有界化（api/services/llm_rate_limit.py + api/services/auth_rate_limit.py）

- `InMemoryLLMRateLimiter._attempts` 与 `AuthRateLimiter._attempts` 换 `OrderedDict` + 键容量上限（`max_keys` 构造参数注入，默认取 `RATE_LIMITER_MAX_KEYS=10000`）：命中（含被拒绝）即 `move_to_end`，新键入库前超容量 `popitem(last=False)` 淘汰最久未用键
- 原 defaultdict 在 consume 时隐式建键，改造后显式建键，淘汰真正发生在插入之前
- Redis 变体主路径不改（键自带 TTL 天然有界）；Redis 故障降级用的进程内 fallback 继承同一容量上限，避免退化后无界增长
- 防御性兜底：`max_keys` 被误配成 0/负数时退化为最小容量，而不是 `popitem` 抛 KeyError 把请求打成 500

## 配置项

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LLM_SESSION_START_IP_LIMIT` | 50 | 匿名访客 session_start 的 IP 维度兜底上限（visitor ×5） |
| `LLM_REPLY_IP_LIMIT` | 150 | 匿名访客 reply（含 stream）的 IP 维度兜底上限（visitor ×5） |
| `RATE_LIMITER_MAX_KEYS` | 10000 | 进程内限流字典键容量上限（LRU 淘汰；仅内存实现，Redis 变体不受影响） |

## 权衡记录

- **fail-closed 重新签发而非 401**：匿名演示是产品入口，报错伤害转化；重新签发后攻击者只是"换个新身份"，配合 IP 兜底限流，收益被压到"合法新访客"水平
- **不做服务端访客会话表**：访客实体落库是审计报告的 Better long-term fix，涉及数据模型与迁移，超出本批次最小修复边界
- **IP 限额只覆盖 sessions 三端点**：media 上传限流属审计 Finding 2，auth 限流的反代头处理属 Finding 5，密钥分离属 Finding 4，各归其位

## 测试与验证

- 全量门禁：`uv run pytest tests` **249 passed, 2 skipped**；`uv run ruff check api tests tools` All checks passed；`uv run black --check api tests tools` 115 files unchanged
- 新增：`tests/core/test_security.py`（签名往返/篡改/错误密钥/截断/畸形输入/value 含点号）、`tests/services/test_auth_rate_limit.py`（容量淘汰/活跃键保温/reset/零容量误配）、`tests/services/test_llm_rate_limit.py` 追加容量淘汰与零容量误配
- `tests/api/test_session_routes.py` 追加：伪造 Cookie 被拒并重签（伪造值不进 owner）、伪造值访问不存在会话仍 404 不 500、有效签名 Cookie 不重设、旧版未签名 Cookie 重签、同 IP 轮换 Cookie 超 IP 限额 429、认证用户连发不耗 IP 配额
- `tests/integration/test_mock_smoke.py` 的固定访客 Cookie 改用 `sign_value` 生成（旧裸 id 会被验签拒绝重签）

## 遗留与后续批次

- 审计 Finding 2：media 上传先整包读内存 + 端点无限流
- 审计 Finding 4：`AUTH_JWT_SECRET` 一钥多用途（JWT / cursor / 访客 Cookie），需密钥分离
- 审计 Finding 5：auth 限流的反代头处理
- 长期：访客实体落库（服务端访客会话表）替代 Cookie 自证身份
