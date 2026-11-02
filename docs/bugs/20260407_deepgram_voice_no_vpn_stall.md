# Bug: 国内无 VPN 环境下 Deepgram 语音回复经常卡在 thinking

## 状态

- `status`: `in_progress`
- `module`: `session_orchestration`
- `related_feature`: `docs/features/deepgram_voice_agent/feature.md`

## 现象

- 关闭 VPN 后，语音会话可以建立，但在实际对话中经常出现明显卡顿。
- 典型表现是用户说完后长时间停留在 `AgentThinking`，迟迟不进入 `AgentStartedSpeaking`。
- 同机同网下，参考项目 `F:\Python\learn\flask-agent-function-calling-demo` 的主观流畅度明显更好。

## 复现条件

1. 在国内网络环境下启动 EchoWhale 前后端。
2. 关闭 VPN。
3. 进入语音练习页并启动 Deepgram Voice Agent。
4. 连续进行多轮口语对话。
5. 观察到 `thinking` 阶段频繁拉长，甚至停在等待态。

## 根因

- EchoWhale 原先的实时语音链路虽然是浏览器直连 Deepgram，但每轮 `think` 仍会走自定义 `agent.think.endpoint`。
- 这条热路径实际是 `Deepgram 云端 -> 公网回调地址 -> EchoWhale -> 外部 OpenAI-compatible 上游`，比参考 Flask 项目多出一段公网回调和一层额外上游调用。
- 在国内无 VPN 网络下，这条链路更容易放大跨网络抖动，导致 `AgentThinking -> AgentStartedSpeaking` 延迟明显增加。
- 前端 hook 此前缺少初始化超时和思考超时保护，所以一旦上游响应过慢，页面容易卡在模糊等待态。
- 即使移除了 think proxy，前端原来的音频热路径仍然偏保守：默认 `AudioContext`、`ScriptProcessor(4096)` 和“上一块播完再播下一块”的串行播放方式，都会继续放大主观卡顿和爆音。

## 修复

- 保留浏览器直连 Deepgram，不改 bootstrap 契约。
- 从实时语音 `agent_settings` 中移除自定义 `agent.think.endpoint`，改成原生 `provider + prompt` 路径。
- 保留现有 `/api/v1/deepgram/think/chat/completions` 作为遗留兼容代理，不再让它成为语音主链路依赖。
- 前端 `useDeepgramVoiceAgent` 新增：
  - 初始化超时
  - `AgentThinking` 超时
  - 超时后的明确错误与状态回收
  - `init_phase / thinking_stall_ms` 诊断字段
- 前端 `useDeepgramVoiceAgent` 再补：
  - `AudioContext({ latencyHint: 'interactive' })`
  - `ScriptProcessor(1024)` 优先，失败时回退到 `2048 / 4096`
  - 单声道、`ideal 16kHz` 麦克风约束
  - `nextPlayTime` 连续播放排程与打断时立即清空
  - `processor_buffer_size / input_context_sample_rate / track_sample_rate / playback_gap_resets` 诊断字段
- 后端 `voice/bootstrap` 新增 Flux `eot_threshold / eager_eot_threshold` 和可配置 `output_sample_rate`
- 修正：`eot_timeout_ms` 不再下发到 Voice Agent `agent.listen.provider`，否则 Deepgram 会返回 `Error parsing client message`
- 修正：`smart_format` 也不再在 `flux-general-en` 的 Voice Agent `listen.provider` 下发，因为该字段不能与 Flux 一起使用

## 验证

- 后端：`uv run pytest tests/integrations/test_deepgram_voice_agent.py tests/core/test_config.py -q`
- 前端：`npm test -- --run src/hooks/useDeepgramVoiceAgent.test.tsx`

## 仍待补充

- 还需要一次真实国内无 VPN 网络下的人工 smoke，确认体感流畅度已经明显接近参考项目。
- 当前实时 spoken reply 更依赖 Deepgram 原生 `think`，因此不会与 EchoWhale 文本链路里的 `coach_engine` 逐轮输出完全一致。
- 若外放仍有杂音，需要再区分“链路抖动”与“扬声器回采”两类问题；耳机 smoke 更能说明真实链路效果。
