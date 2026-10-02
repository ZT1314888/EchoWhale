# 限流体系收口（ratelimit_closing）

> 审计报告（audit-report-EchoWhale-2026-10-01.md）Finding 5 / Finding 12 修复。
> Trellis 任务：`.trellis/tasks/10-01-ratelimit-closing`。

## 目标

三条限流面收口：①`AuthRateLimiter` 只有进程内实现（多 worker 配额按进程数倍增；反代后全站共享 login 桶可被故意打满）；②`/sessions/{id}/voice/bootstrap` 无限流（每次调用消耗一次 Deepgram token grant）；③think 代理令牌为 TTL 内可复用的 bearer 能力，`sid` 只用于日志——上游 LLM 成本滥用窗口敞开。

## 实现说明

### 1. AuthRateLimiter Redis 化（F5）

`RedisAuthRateLimiter`（镜像 `RedisLLMRateLimiter`）：固定窗口 INCR + 首次 EXPIRE，保留每 action 个性化超限文案；`RedisError` → 同规则同容量的进程内降级 + `auth_rate_limit_redis_unavailable` warning。工厂分流与 `get_llm_rate_limiter` 口径一致（未配 redis → 进程内；配了没装 → 启动报错）。多 worker / 多实例从此共享计数。

### 2. 语音 bootstrap 限流（F12a）

新 action `voice_bootstrap`（5 次/小时/owner）+ `voice_bootstrap_ip`（25 次/小时/IP）；`bootstrap_voice_session` 用 `consume_with_ip_guard` 在 service 调用之前消耗——Deepgram 令牌签发只发生在限流通过后（测试用 fake issuer 断言"被限流请求零签发"）。`voice/complete` 不限流（纯计算 + DB，无外部成本）。

### 3. think 代理防护（F12b）

处理顺序（每步都有存在理由）：令牌解码（401）→ 上游配置（500）→ body 解析/校验（400）→ **per-sid 限流**（`think_proxy`，120 次/5 分钟，超限 429 OpenAI 形态）→ **sid 存在性**（仓储 PK 查询，不存在含 `sid="unknown"` 统一 401，不泄露会话存在性）→ 转发。限流先于存在性校验：同 sid 洪泛打满配额后不再触碰 DB。

### 4. XFF 立场（零代码改动）

应用不解析 `X-Forwarded-For`（客户端可伪造，等于把限流键交还攻击者）。反代正确性由部署层保证：uvicorn `--proxy-headers --forwarded-allow-ips=<proxy>` 使 `request.client.host` 恢复为真实客户端 IP——已写入 .env.example 部署要求块。

## 验证

- +11 个测试（累计 404 passed / 2 skipped）：auth 限流跨实例共享计数、窗口翻新、RedisError 降级（caplog）、工厂口径；bootstrap owner 超限 / IP 轮换 429 / 认证用户不受影响 / 零签发断言；think 代理未知 sid 401（上游零调用）、per-sid 429、无 sid claim 401。
- ruff / black 全绿。

## 遗留

- think 代理一次性票据（bootstrap 换取、用后即焚）归语音链路演进批次。
- INCR+EXPIRE 非原子的极端窗口残留（crash 在两命令之间）与 LLM 限流器同源，属 Low，统一 Lua 化时一并处理。
