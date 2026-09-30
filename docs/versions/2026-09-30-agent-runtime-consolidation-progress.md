# 2026-09-30 Agent 运行时收敛（第二批架构优化）

## 本轮范围

第一批"正确性与护栏"完成后的第二批收敛，未创建 Trellis 任务（沿用用户决定），docs 留痕照常。

## 生产代码

- 新增 `api/integrations/llm/runtime.py`：
  - `ProviderSlotConfig` + `provider_slot_from_settings`：text/vision 主备槽位配置统一读取
  - `resolve_engine_providers`：收敛两份近乎逐字相同的 26 行 live/mock 分流 + 主备提升逻辑
  - `TextCompletionProvider`：裸文本补全 provider，feedback 引擎接回 provider 抽象（此前在 agent 里内联构造 httpx 客户端）
- coach / scene 引擎四件套脚手架删除（`build_primary_*` / `build_fallback_*` / `has_real_*` / `_build_provider`）
- `session_engine/agent.py`：删除 `inspect.signature` 反射派发（含一个死分支和一处选中即 `TypeError` 的分支），`reply` 与 `complete_voice_session` 直调子引擎
- `session_db.py`：新增 `list_recent_messages`（position 倒序取窗口后回正序）；删除 N+1 的 `list_user_sessions` 全链路（仓储/Protocol/agent/service 包装，无路由调用方）
- `reply()` 读路径：全量会话 → `get_session_head` + `list_recent_messages(LLM_COACH_WINDOW_SIZE)`；写后全量重读保留（响应契约）
- `chat_provider.py`：硬编码 `recent_messages[-4:]` → `settings.llm_coach_window_size`
- `openai.py`：`json_mode` 参数注入 `response_format: {"type": "json_object"}`，配置开关 `LLM_JSON_MODE_ENABLED`（默认关）
- `config.py`：新增 `llm_coach_window_size` / `llm_json_mode_enabled`

## 过程发现

- 冒烟抓到 fake 测试盲区：agent 调用 `list_recent_messages` 曾一度只有 fake 仓储实现、真实仓储缺失，189 个测试全绿但端到端即挂。已补 `list_recent_messages` 的仓储级直接用例堵住盲区
- 本地 `.env` 的 `MODEL_RUNTIME_MODE=live` 会渗入任何冒烟脚本；冒烟时需显式钉 `settings.model_runtime_mode = "mock"`

## 测试与冒烟

- 全量 `uv run pytest tests`：**190 passed, 2 skipped**
- mock 冒烟：三引擎经共享 runtime 解析返回 Mock provider；start → reply×2 → 会话消息 5 条（1 opener + 2 轮 user/assistant）
- live 模式已具备：本机 `.env` 配置真实 OpenAI 兼容端点时 reply 直连成功（端点行为属用户本地配置）

## 遗留

- 第三批：文字回复 SSE 流式、场景分析按 media_id 缓存 + RQ 异步化
- 独立工程：auth 链路迁 async、LLM 滚动摘要（PRD v0.4 会话总结）
