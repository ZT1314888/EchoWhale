# Feature: `think_token_lifecycle_binding`

## 基本信息

- `feature`: `think_token_lifecycle_binding`
- `status`: `feature_test_passed`
- `branch`: `dev`（审计后续批次按既有惯例随 dev 推进）
- `module`: `platform_foundation`
- `cross_module`: `no`（前端零改动）
- `owner`: `lucky`
- `updated_at`: `2026-10-07`
- `merge_target`: `module/platform_foundation`

## 背景

审计 Finding 12 的 minimal fix（30b1768）已落地语音 bootstrap 限流、think 代理
per-sid 配额（120/5min）与 sid 存在性校验，但 think 代理令牌仍是"TTL 内可复用的
bearer 能力"：语音会话结束后令牌依旧有效，重复 bootstrap 也不让旧令牌失效——
这是该 finding 的最后一个滥用窗口（Better fix）。

规划期核实还发现一个前置落差：`DeepgramThinkProxyTokenCodec.issue` 与
`build_deepgram_think_proxy_url` 在生产代码中零消费，`DeepgramSettingsBuilder`
构造的 agent_settings 不含 `think.endpoint`（有测试显式断言）——即 bootstrap 从未
真正把 think 令牌交给 Deepgram，代理校验链只被测试铸出的令牌命中；api.md
"语音 bootstrap 签发"的描述与实现存在落差。本批次把签发接线一并补全。

## 用户故事

- 当我的语音练习结束时，我希望 think 代理令牌即刻失效，这样被截获的令牌不能在
  会话结束后继续消耗上游 LLM 成本。
- 当我在同一会话重复启动语音时，我希望旧令牌作废、只有最新一次 bootstrap 签发的
  令牌可用，这样令牌能力始终与当前活跃语音会话一一对应。

## 范围

### In scope

- 方案 A（生命周期绑定）：`voice_session_facts` 增 `token_generation` 计数
  （迁移 20261007_0016，可逆），每次 bootstrap +1；收口路径回带计数不清零。
- think 代理令牌 payload 在 `sid` 之外携带 `gen` claim（`issue` 默认 0，bootstrap
  显式传代数）。
- 签发接线：`bootstrap_voice_session` 在配置了 `DEEPGRAM_AGENT_THINK_PROXY_PUBLIC_BASE_URL`
  时按代数签发 think 令牌并内嵌 `agent.think.endpoint`（Deepgram BYO LLM 形态，
  url + headers）；未配置时行为与历史版本逐字节一致。bootstrap 响应 schema 与
  前端零改动（agent_settings 对前端是不透明 dict）。
- 代理校验链追加生命周期校验（顺序不变：解码 401 → 上游配置 500 → body 400 →
  per-sid 限流 429 → sid 存在 + 生命周期 401 → 转发）：fact 存在 + `status=active`
  + 代数一致；缺 gen claim / 非整数 fail-closed。所有生命周期类拒绝统一 401
  authentication_error，不泄露原因；拒绝原因只进服务端 key=value 日志。

### Out of scope（遗留）

- 方案 B 一次性票据：防的是"bootstrap 响应被截获后延迟使用"，而 TLS 之后的截获面
  + 5 分钟 TTL + bootstrap 5/h(owner) / 25/h(IP) 配额已把收益压到极低，且需前端
  新增换票步骤；维持控制面既有"独立立项"登记。
- Deepgram 语音令牌自身生命周期（TTL 语义属 Deepgram 侧）。
- registry 推送流水线（等用户定 registry）。
- PG 口径迁移 downgrade 实测与全仓储 PG 参数化（后续批次；0016 down 脚本照常写，
  可逆性用例按既有 sqlite_only 约定处理）。
- 前端 useDeepgramVoiceAgent hook 重构。

## 设计要点

- 关键流程：bootstrap 读 fact 算代数 → 签语音令牌（失败上抛 1302/503，代数不落库，
  无空洞）→ （门控）签 think 令牌 + 构造 endpoint → settings build 透传 →
  fact 落库（active, generation）→ 事件落库；complete 收口 fact 转 completed 并
  回带 generation。
- 关键数据：`voice_session_facts.token_generation`（Integer NOT NULL，
  server_default "0"——迁移前旧行语义为"无活跃绑定"，与 fail-closed 校验自洽）。
- 依赖模块：`api/integrations/deepgram`（codec/Protocol/builder）、
  `api/modules/session_engine`（编排）、`api/routes/v1/deepgram.py`（校验链）、
  `api/db/session_db.py`（仓储透传）、迁移 0016。
- 失败时如何处理：校验失败一律 401 authentication_error（与既有 401 同形，
  防枚举）；fact PK 点查与 sid 存在性同级别，不合 JOIN（head 承担归属接缝、
  fact 承担生命周期，各自复用既有 Protocol 方法）。
- 并发语义：并发 bootstrap 可能读到同一代数——重复 bootstrap 本就是允许语义，
  计数目标是让旧令牌失效而非严格唯一性；滥用面由 bootstrap 限流封顶。
- 回滚：代码 revert 即可（列是纯附加物，旧代码不感知）；数据 downgrade 可选。

## 验收标准

- [x] voice/complete 后未过期 think 令牌被拒（401），有测试锁定。
- [x] re-bootstrap 后旧 generation 令牌被拒、新代数令牌可用，有测试锁定。
- [x] 活跃会话正常 think 调用不受影响：既有 mock upstream 用例零改动通过
      （仅共享替身补 `get_latest_voice_session_fact`，`issue()` 默认代数 0 保证
      既有铸令牌调用点语义不变）。
- [x] 未配置 proxy base URL 时 bootstrap 行为与现状一致（settings builder 既有
      断言保持绿）；配置后 endpoint 内嵌且令牌 sid/gen 与 fact 一致。
- [x] 401 不泄露拒绝原因（四类生命周期拒绝共用同一 message/type，另有逐字节
      同形断言）。
- [x] 迁移 0016 可逆（可逆性用例 sqlite_only，理由成文）。
- [x] docs/api.md §11 与端点表、PRD §4.7/§7.6 同步。

## 测试记录

- `feature_test_passed` 的证据（2026-10-07）：
  - SQLite 口径：`MODEL_RUNTIME_MODE=mock uv run pytest tests --cov=api` →
    **647 passed / 9 skipped**，覆盖率 **89.65%**（基线 635/9、89.56% 只升不降）。
  - PG 口径：本地真实 PG 独立库 echowhale_ci（`ECHOWHALE_TEST_DATABASE_URL`）→
    **642 passed / 14 skipped**（基线 631/13：+11 为本批新用例、+1 为 0016 可逆性
    用例 sqlite_only 显式 skip），验证后测试库已删除。
  - 新增测试 12 个：路由层生命周期拒绝 4（completed / 代数不匹配 / 缺 gen claim /
    fact 缺失，含 401 同形与"不转发上游"断言）、integrations 3（codec gen claim
    显式/默认、builder endpoint 两态）、模块层 4（配置态签发接线 / re-bootstrap
    代数递增 / 未配置态零签发 / 收口回带代数）、迁移可逆性 1。
  - `uv run ruff check api tests tools`、`uv run black --check api tests tools` 全绿。
  - 前端零改动，回归门禁全绿：`npm run lint`、`npm run typecheck`、
    `npm run coverage`（vitest 115 passed，四阈值 86.35/77.81/84.1/86.35 ≥
    76/74/78/76）。
- 主要测试命令：见上。
- 已知缺口：实施期一处规划修订——voice_bootstrapped 事件 payload 未加
  `token_generation`（既有模块用例逐字节断言 payload，零改动原则优先；代数留痕由
  fact 行承载）；flake 根因修复：新增 bootstrap 用例补 `FakeVoiceTokenIssuer`
  替身，杜绝真签发器在 live .env 下打真实 Deepgram Auth API 的网络依赖。

## 控制面同步

- `docs/control/agent-control-plane.json` 已增 feature 行并 `render` / `check`。

## 合并与关闭

- 随 dev 推进，`feature_test_passed` 即达成；`merged_to_module` / `closed` 待
  控制面批次收口惯例。
- 相关文档：docs/api.md §11、docs/prd.md §4.7/§7.6、
  `.trellis/tasks/10-07-think_token_lifecycle_binding/`（prd/design/implement）。
