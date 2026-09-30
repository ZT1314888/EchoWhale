# Bug: `deepgram-voice-bootstrap-token-error`

## 基本信息

- `bug`: `deepgram-voice-bootstrap-token-error`
- `status`: `feature_test_passed`
- `branch`: `bugfix/session_orchestration/deepgram-voice-bootstrap-token-error`
- `owner`: `codex`
- `reported_at`: `2026-04-06`
- `affected_area`: `session_orchestration`

## 现象

真实上传图片后进入语音练习页，点击 `Talk To Your Agent` 会在 `POST /api/v1/sessions/{session_id}/voice/bootstrap` 阶段报 500。服务端栈追踪里能看到 `httpx.LocalProtocolError: Illegal header value b'Token '`。

## 复现步骤

1. 启动本地后端与前端。
2. 上传一张真实图片，创建真实 `sess_*` 会话。
3. 进入练习页并点击 `Talk To Your Agent`。
4. 观察后端日志和接口响应。

## 预期结果

- Deepgram token 成功签发并返回 `voice/bootstrap` 响应。
- 如果 Deepgram 配置缺失或 token 获取失败，接口返回明确的应用层错误，而不是 500 栈追踪。

## 实际结果

- `voice/bootstrap` 在调用 Deepgram SDK 时直接抛底层异常。
- 异常穿透到全局 500 处理，前端只能看到泛化失败。
- 当运行进程吃到空白 `DEEPGRAM_API_KEY` 时，请求头会被拼成非法的 `Authorization: Token `。
- 在浏览器直连 Deepgram Voice Agent 的阶段，前端最初使用 `?token=` query 参数建立 WebSocket，不符合官方当前对 client-side Voice Agent 的鉴权建议。
- 在拿到有效 token 并建立 Voice Agent 连接后，Deepgram 又会校验 `agent_settings`。旧实现只发送了 `agent.think.prompt`，缺少官方要求的 `agent.think.provider`，因此会报 `Error parsing client message. Check the agent.think field against the API spec.`。

## 影响范围

- 用户影响：真实语音练习主链路无法启动，上传后的练习页被阻断。
- 模块影响：`session_orchestration` 的 Deepgram bootstrap 缺少配置门禁和错误收口。
- 运维影响：修改 `.env` 后如果不重启进程，服务仍可能持有旧配置并继续报错。

## 根因

- `api/core/config.py` 之前没有把 Deepgram voice 配置纳入运行时校验，生产环境缺配置时不会提前失败。
- `api/integrations/deepgram/voice_agent.py` 直接把 `settings.deepgram_api_key` 传给 SDK，未对空值和 SDK/HTTP 异常做应用层翻译。
- 设计文档虽然定义了 `1302 Deepgram token 获取失败`，但代码里没有实现对应异常。
- 前端 `frontend/src/hooks/useDeepgramVoiceAgent.ts` 初版使用 URL query 参数承载临时 token，而不是按 Deepgram 官方文档通过 `Sec-WebSocket-Protocol` 传递浏览器侧鉴权信息。
- 后端生成的 `agent_settings` 未对齐官方 Voice Agent schema：`agent.think` 只有 `prompt`，缺少 `provider`，也没有安全地承载国内 OpenAI-compatible 网关所需的代理 endpoint。

## 修复方案

- 改了什么：
  - 在 `api/common/exceptions.py` 新增 `VoiceTokenError`，统一承接 Deepgram token 获取失败，错误码为 `1302`。
  - 在 `api/core/config.py` 增加生产环境下的 `DEEPGRAM_API_KEY` 和 `DEEPGRAM_AGENT_BASE_URL` 校验。
  - 在 `api/integrations/deepgram/voice_agent.py` 中：
    - 对空白 `DEEPGRAM_API_KEY` 直接抛 `ConfigurationError`
    - 对 Deepgram SDK / HTTP 层失败统一抛 `VoiceTokenError`
  - 在 `api/main.py` 启动时增加脱敏日志，标记 Deepgram voice 配置是否已就绪。
  - 在 `frontend/src/hooks/useDeepgramVoiceAgent.ts` 中把浏览器直连 Deepgram Voice Agent 的鉴权方式改成 `new WebSocket(url, ["bearer", token])`，让浏览器通过 `Sec-WebSocket-Protocol` 发送临时 token。
  - 在 `api/integrations/deepgram/voice_agent.py` 中补齐符合官方 schema 的 `agent.think.provider` / `agent.think.endpoint`，并生成 session 绑定的短期 think proxy token。
  - 新增 `POST /api/v1/deepgram/think/chat/completions` 作为 Deepgram `agent.think.endpoint` 代理，由服务端私有凭证转发到国内 OpenAI-compatible 网关。
  - 在 `api/core/config.py` 与 `.env.example` 中补齐 `DEEPGRAM_AGENT_THINK_*` 配置，明确要求公网可访问的 think proxy base URL 和上游网关凭证。
  - 增加配置级、集成级和 API 级回归测试。
  - 增加前端 hook 回归测试，锁定 WebSocket 必须使用 bearer subprotocol，而不是把 token 放进 query string。
- 为什么这样改：
  - 这是典型的外部集成边界问题，应该在配置层和 adapter 层做双重防守，而不是让底层库异常直接进入路由层。
  - 保持现有前端契约不变，只把错误语义从“500 崩溃”提升为“可识别、可诊断”的应用错误。
- 是否有兼容性风险：
  - 风险低；成功路径的 bootstrap 数据结构不变，只新增失败态门禁和异常翻译。

## 验证

- 测试命令：
  - `python -m pytest tests/integrations/test_deepgram_voice_agent.py tests/api/test_session_routes.py -q`
  - `uv run pytest tests/integrations/test_deepgram_voice_agent.py tests/api/test_deepgram_routes.py tests/core/test_config.py -q`
  - `npm test -- src/hooks/useDeepgramVoiceAgent.test.tsx`
  - 定向配置验证脚本：分别构造缺失 `DEEPGRAM_API_KEY` / `DEEPGRAM_AGENT_BASE_URL` 的生产环境 `Settings`，确认 `validate_runtime()` 抛 `ConfigurationError`
- 验证结果：
  - API 与集成定向测试通过，`15 passed`。
  - Deepgram settings / think proxy / config 定向测试通过，确认 `agent.think` 已补齐 `provider + endpoint`，且代理路由能按 OpenAI-compatible 协议转发。
  - 前端 hook 定向测试通过，确认当前使用 `Sec-WebSocket-Protocol` bearer 子协议建连。
  - 配置定向脚本验证通过，两个新门禁都能准确抛出对应配置错误。
- 仍需关注：
  - 本地 `pytest` 的 `tmp_path` 临时目录在当前 Windows 环境有 ACL 问题，导致 `tests/core/test_config.py` 无法直接通过 pytest 跑完；本次已用等价脚本确认新增门禁逻辑正确。
  - 若本地服务进程是在补全 `.env` 之前启动的，仍需手动重启后端进程以加载新配置。

## 关闭条件

- 从 `in_progress` 到 `feature_test_passed`：Deepgram token 获取失败不再以 500 栈追踪暴露，且定向验证通过。
- 从 `feature_test_passed` 到 `merged_to_module`：代码与 bug 文档合入 `session_orchestration` 模块分支。
- 从 `merged_to_module` 到 `closed`：真实 `upload -> session -> voice/bootstrap` 联调稳定，不再出现 `Illegal header value b'Token '` / `agent.think` schema 回归，且浏览器直连 Voice Agent 使用官方推荐的 `Sec-WebSocket-Protocol` 鉴权方式。
