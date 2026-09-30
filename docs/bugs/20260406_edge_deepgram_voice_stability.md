# Bug: Edge 实时语音会话启动失败与回复颤音

## 状态

- `status`: `in_progress`
- `module`: `frontend_app`
- `related_feature`: `docs/features/deepgram_voice_agent/feature.md`

## 现象

- 在 Edge 浏览器点击语音练习后，会话可能直接报 `Failed to think. Please check your agent.think settings.`
- 即使会话能连上，agent 回复音频也会出现不顺畅、颤音或明显回声

## 复现条件

1. 使用 Edge 打开练习页
2. 启动 Deepgram Voice Agent 会话
3. 在 agent 首轮欢迎后继续说话，或等待 agent 返回语音
4. 观察到启动阶段直接失败，或播放时出现回声/颤音

## 根因

- 前端采集链路把 `ScriptProcessorNode` 直接接到了 `AudioContext.destination`，浏览器会把用户麦克风原声回放到扬声器，与 agent 输出叠加后形成回声和颤音。
- 前端启动阶段如果 WebSocket 在 `SettingsApplied` 前关闭，hook 只清空状态，不会 reject 初始化 Promise，页面会停在模糊失败状态。
- 后端 `agent.think` 代理此前把多类错误都折叠成配置错误，并假定上游始终返回 JSON，导致真实上游坏请求或 HTML 错误页被吞掉，浏览器侧只能看到 Deepgram 的通用报错。
- Deepgram 发送到自定义 `agent.think.endpoint` 的请求会触发流式 `chat/completions` 响应；SiliconFlow 在该场景下返回 `text/event-stream`，而旧代理固定调用 `response.json()`，把合法的 SSE 响应误判成“非 JSON”，最终向 Deepgram 返回 502。

## 修复

- 前端把采集输出改为静音 `GainNode`，保留 PCM 发送但不再本地放音。
- 前端补充启动阶段关闭的明确失败路径，并把 `browser / last_agent_event / last_agent_error` 一并带到 `voice/complete`。
- 前端播放队列加入 generation 保护，避免用户打断后旧音频块继续排队播放。
- 后端代理把鉴权失败、配置失败、坏请求、上游网络失败和上游非 JSON 响应拆分处理，并记录脱敏诊断日志。
- 后端代理新增 `stream=true` 分支：对 `text/event-stream` 上游响应直接透传 SSE；如果流式请求下上游返回的是普通 JSON 错误体，也按原状态码和错误结构透传，不再错误折叠成 502。

## 验证

- 前端：`npm test -- --run src/hooks/useDeepgramVoiceAgent.test.tsx src/pages/PracticeSessionPage.test.tsx src/services/sessionApi.test.ts`
- 后端：`uv run pytest tests/api/test_deepgram_routes.py tests/api/test_session_routes.py tests/integrations/test_deepgram_voice_agent.py -q`

## 仍待补充

- 需要在真实 Edge + 麦克风 + 扬声器环境补一次完整 smoke，确认体感卡顿和颤音确实消失
- 需要观察一次真实 `agent.think` 上游失败日志，确认代理返回的错误分类足够覆盖线上情况
