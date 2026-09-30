# Feature: `deepgram_voice_agent`

## 目标

将练习页从浏览器本地 `Web Speech API` 转写切换为 Deepgram Voice Agent 全语音链路，同时保留 EchoWhale 的场景初始化、session 落库、history 和练后 review。

## 当前实现

- 后端新增：
  - `POST /api/v1/sessions/{session_id}/voice/bootstrap`
  - `POST /api/v1/sessions/{session_id}/voice/complete`
  - `POST /api/v1/deepgram/think/chat/completions`
- `voice/bootstrap` 负责：
  - owner 校验
  - 下发 Deepgram token
  - 组装符合官方 schema 的 Agent `Settings`
  - 下发原生 `agent.think.provider + prompt`，不再把自定义 `endpoint` 放入实时语音热路径
  - 返回当前 session 快照
- `deepgram/think/chat/completions` 负责：
  - 保留为遗留兼容代理入口
  - 校验短期代理 token
  - 在需要时以 OpenAI-compatible 协议转发到服务端私有网关
- `voice/complete` 负责：
  - 接收前端累计的 `ConversationText`
  - 回写 transcript 到现有 `session.messages`
  - 调用 `feedback_engine` 生成练后 review
- 前端新增 `useDeepgramVoiceAgent`：
  - 建立 Deepgram WebSocket
  - 等待 `Welcome -> SettingsApplied`
  - 采集麦克风 PCM
  - 播放 agent 返回音频
  - 实时显示 transcript
  - 结束会话后调用 `voice/complete`
- 2026-04-06 稳定性补丁：
  - 采集链路改为静音 `GainNode` 输出，避免麦克风原声直通扬声器导致回声和颤音
  - 启动阶段若 WebSocket 在 `SettingsApplied` 前关闭，会明确报错而不是悬挂在等待态
  - `voice/complete` 现在会回写浏览器侧诊断字段，例如 `browser / last_agent_event / last_agent_error`
  - `deepgram/think/chat/completions` 现在区分鉴权、配置、坏请求、上游网络失败和上游非 JSON 响应，并写脱敏日志
- 2026-04-07 国内网络流畅度补丁：
  - 浏览器仍直连 Deepgram，但实时语音不再依赖 `agent.think.endpoint`
  - `agent.think` 改为原生 `provider + prompt` 路径，减少 `Deepgram 云端 -> 公网回调 -> EchoWhale -> 外部上游` 带来的额外抖动
  - 前端新增初始化超时和 `AgentThinking` 超时保护，避免会话卡死在等待态
  - `voice/complete` 现在额外回写 `init_phase / thinking_stall_ms`
  - 麦克风采集改为低延迟参数：`AudioContext({ latencyHint: 'interactive' })` + `ScriptProcessor(1024)` 优先，并强制单声道 / `ideal 16kHz`
  - 播放链路改为 `nextPlayTime` 连续排程，减少 chunk 之间的爆音和停顿
  - Deepgram `listen.provider` 增加 Flux turn-taking 参数：`eot_threshold / eager_eot_threshold`
  - `eot_timeout_ms` 仅保留为本地预留配置，不再下发到 Voice Agent `Settings`，因为该字段不在当前 Voice Agent `agent.listen.provider` schema 内
  - `smart_format` 也不再在 Flux listen provider 下发，Deepgram Voice Agent 文档示例明确说明该字段不能与 Flux 一起使用
  - `voice/complete` 现在会额外回写 `processor_buffer_size / input_context_sample_rate / track_sample_rate / playback_gap_resets`
- 2026-04-07 会话页布局补丁：
  - `PracticeSession` 桌面端从单栏语音舞台调整为“左侧鲸鱼 logo 主舞台 + 右侧实时对话”的双栏布局
  - 左栏不再保留标题、开场提示和文本按钮；鲸鱼 logo 本身兼任 start/end 控制，并在点击后切到持续 wifi 动效
  - 右栏承接会话标题、角色状态与消息流
  - 实时 transcript 与已有消息现在会在新增时自动滚动到最新位置
  - 消息区滚动条视觉已隐藏，避免右侧出现明显拖拽条观感

## 边界

- `scene_engine` 继续负责 `scene / role / opener / visual_anchors / vocab_candidates`
- Deepgram Agent 接管实时 `listen -> think -> speak`
- 实时 `think` 走 Deepgram 原生 provider 路径，不再依赖公网 think proxy
- `feedback_engine` 当前仍用于结束后的 review 生成，不再作为语音页逐轮实时反馈
- 旧 `/sessions/{id}/reply` 文本链路暂时保留兼容，但语音页不再调用

## 验证证据

- 后端：`uv run pytest tests/modules/test_session_engine.py tests/api/test_session_routes.py -q`
- 后端：`uv run pytest tests/integrations/test_deepgram_voice_agent.py tests/api/test_deepgram_routes.py tests/core/test_config.py -q`
- 后端：`uv run pytest tests/api/test_deepgram_routes.py tests/api/test_session_routes.py tests/integrations/test_deepgram_voice_agent.py -q`
- 前端：`npm test -- --run src/hooks/useDeepgramVoiceAgent.test.tsx src/pages/PracticeSessionPage.test.tsx src/services/sessionApi.test.ts`
- 前端：`npm test -- --run src/hooks/useDeepgramVoiceAgent.test.tsx`
- 前端：`npm test -- --run src/pages/PracticeSessionPage.test.tsx`

## 剩余风险

- 真实 Deepgram token 与生产环境网络联调还未验证
- 语音链路的实时回复流畅度会更接近 Deepgram 原生体验，但不会与 EchoWhale 文本 `coach_engine` 的逐轮回复完全一致
- 真实 Edge 浏览器 + 麦克风 + 扬声器的一次完整 smoke 还未补
- `autoGainControl` 已关闭以减少泵音和杂音，但不同设备在外放场景下仍可能出现声学回采，最好用耳机再做一次对比 smoke
- 历史页当前回放的是最终 transcript 落库结果；虽然已把诊断字段带到 `voice/complete`，但历史页还未暴露这部分调试信息
