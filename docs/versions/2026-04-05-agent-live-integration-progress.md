# Version: `2026-04-05-agent-live-integration-progress`

## 基本信息

- `version`: `2026-04-05-agent-live-integration-progress`
- `status`: `integrating`
- `branch`: `module/session_orchestration`
- `created_at`: `2026-04-05`
- `published_at`: ``

## 版本摘要

今天完成了 EchoWhale 第一轮 agent live 联调：四模型主备配置已切到 `live + openai_compatible`，文本主模型、`coach_engine`、`feedback_engine` 与视觉主模型都已验证可用；其中视觉主模型已成功处理“项目真实上传到 R2 后生成的签名 URL”。当前系统已经从“可跑 mock agent”推进到“主模型可执行真实图片理解与文本生成”的阶段，但视觉兜底模型仍不可用，文本兜底模型对结构化 JSON 输出仍不稳定。

## 包含内容

- `api/`
  - 更新 `api/core/config.py`
  - 更新 `api/integrations/llm/base.py`
  - 更新 `api/integrations/llm/openai.py`
  - 更新 `api/modules/scene_engine/agent.py`
  - 更新 `api/modules/scene_engine/providers/vision_provider.py`
  - 更新 `api/modules/scene_engine/service.py`
  - 更新 `api/modules/coach_engine/schema.py`
  - 更新 `api/modules/coach_engine/agent.py`
  - 更新 `api/modules/coach_engine/providers/chat_provider.py`
  - 更新 `api/modules/coach_engine/service.py`
  - 更新 `api/modules/feedback_engine/schema.py`
  - 更新 `api/modules/feedback_engine/agent.py`
  - 更新 `api/modules/feedback_engine/service.py`
  - 更新 `api/modules/session_engine/agent.py`
- `tests/`
  - 新增 `tests/modules/test_scene_engine.py`
  - 新增 `tests/modules/test_coach_engine.py`
  - 新增 `tests/modules/test_feedback_engine.py`
  - 更新 `tests/core/test_config.py`
  - 更新 `tests/modules/test_session_engine.py`
- `docs/`
  - 更新 `docs/control/project-index.md`
  - 更新 `docs/modules/scene_engine/status.md`
  - 更新 `docs/modules/coach_engine/status.md`
  - 更新 `docs/modules/feedback_engine/status.md`
  - 新增本进度快照
- `env/`
  - 更新 `.env.example`
  - 本地 `.env` 已追加四模型接入占位键并切到 live provider 开关

## 完成情况

- 已完成：
  - 四模型接入入口已预留：视觉主模型 / 视觉兜底 / 文本主模型 / 文本兜底
  - 运行模式已支持 `MODEL_RUNTIME_MODE=mock|live`
  - 视觉主模型已通过真实上传图片的 R2 签名 URL 联调
  - 文本主模型已通过直接 smoke test、`coach_engine` live 与 `feedback_engine` live 验证
  - `feedback_engine` 已支持图片 `labels` 优先进入 `Useful Words`
  - `session_engine` 已能把 session `labels` 与最近消息传给下游文本链路
- 未完成但可接受：
  - 视觉兜底模型当前返回 `403 Model disabled`
  - 文本兜底模型普通文本请求可通，但在 JSON-only 结构化任务上超时或断开
  - 还未完成一次完整的真实 `upload -> session -> reply -> review` 全链路 smoke test
- 已知限制：
  - 视觉主链路依赖真实上传后的图片 URL；任意外部图片源并不保证都能被 SiliconFlow 处理
  - 当前最稳定的是主模型链路，兜底策略仍需换模型或继续联调

## 验证结果

- backend：
  - 执行 `uv run pytest -q`
  - 结果：`62 passed, 1 skipped`
- frontend：
  - 执行 `npm run build`
  - 结果：构建通过，产物写入 `frontend/dist/`
  - 执行 `npm test`
  - 结果：存在 1 个既有 auth 前端用例失败，失败点与本轮 agent 集成无关
- live smoke：
  - 文本主模型：成功返回 `TEXT_PRIMARY_OK`
  - `coach_engine` live：成功返回真实追问文本
  - `feedback_engine` live：成功返回结构化反馈
  - 视觉主模型：对 SiliconFlow 文档样例图可用；对项目真实上传的 R2 签名 URL 也可用
  - 视觉兜底模型：`403 Model disabled`
  - 文本兜底模型：结构化 JSON 请求下超时或连接中断

## 关键结论

- 当前 EchoWhale 已具备“主模型可看图并生成背景/角色/开场对话，再继续文本陪练”的真实能力。
- 真实上传后的 R2 签名 URL 不是阻塞项；视觉主模型已经成功处理项目自己的上传产物。
- 当前阻塞上线稳定性的主要问题不在主链路，而在两条兜底链路：
  - 视觉兜底模型不可用
  - 文本兜底模型不适合当前 JSON 结构任务

## 后续工作

- 下一版要补什么：
  - 更换视觉兜底模型为可用模型
  - 更换文本兜底模型为更稳定的非-thinking / JSON 友好模型
  - 完成一次真实 `upload -> session -> reply -> review` 全链路 smoke test
  - 视需要收紧视觉 prompt 和文本 JSON 约束
- 哪些 feature 仍在 `planned` 或 `in_progress`：
  - `scene_engine` 仍在 `building`，需继续处理视觉兜底策略
  - `coach_engine` 仍在 `building`，需继续验证多样本输出稳定性
  - `feedback_engine` 仍在 `building`，需继续验证兜底 JSON 结构稳定性
  - `session_orchestration` 仍在 `building`，待完成真实全链路 smoke test
