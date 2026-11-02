# Feature: `agent_runtime_consolidation`

## 基本信息

- `feature`: `agent_runtime_consolidation`
- `module`: `platform_foundation`（LLM 共享底座）
- `status`: `feature_test_passed`
- `updated_at`: `2026-09-30`

## 目标

第二批架构收敛：消除三套引擎间的复制粘贴脚手架、定死子引擎接口、修复 DB 读放大与 N+1，并为 JSON mode 与上下文窗口建立配置入口。

## 共享 provider 解析（api/integrations/llm/runtime.py）

- `ProviderSlotConfig` + `provider_slot_from_settings(kind, slot)`：统一从 settings 读取 text/vision 主备槽位
- `resolve_engine_providers(...)`：把原先两份近乎逐字相同的 26 行 `__init__` 分流逻辑（live/mock 门禁、主备提升）收敛为一处
- `TextCompletionProvider`：裸文本补全 provider，让反馈引擎接回 provider 抽象，不再在 agent 里内联构造 httpx 客户端
- coach / scene 引擎的四件套脚手架（`build_primary_*` / `build_fallback_*` / `has_real_*` / `_build_provider`）全部删除

## 接口定死（session_engine/agent.py）

- 删除 `inspect.signature` 运行时反射派发：里面有一个死分支和一处选中即 `TypeError` 的分支，一直在掩盖编排层与子引擎接口漂移
- `reply()` 与 `complete_voice_session()` 直调 `feedback_engine.review(...)` / `coach_engine.respond(...)`

## DB 读放大与 N+1

- `reply()` 读路径从"全量会话"改为 `get_session_head` + `list_recent_messages(limit)`（`LLM_COACH_WINDOW_SIZE`，默认 8）；写后的全量重读保留（响应契约需要完整消息列表）
- 仓储新增 `list_recent_messages`（按 position 倒序取窗口后回正序），并补仓储级直接用例
- 删除 N+1 的 `list_user_sessions` 全链路（仓储方法、Protocol 声明、agent/service 包装）——它没有任何路由调用方，历史列表一律走已优化的分页版

## coach 上下文窗口

- 硬编码的 `recent_messages[-4:]` 改为 `settings.llm_coach_window_size`，单轮注入的对话窗口可调

## JSON mode

- `OpenAICompatibleClient` 支持 `json_mode` 参数（payload 注入 `response_format: {"type": "json_object"}`）
- 配置项 `LLM_JSON_MODE_ENABLED`（默认关闭）：部分 OpenAI 兼容端点不支持该字段，故保守开关

## 测试与验证

- 全量 `uv run pytest tests`：**190 passed, 2 skipped**
- 仓储级新增 `list_recent_messages` 直接用例——起因是冒烟发现 fake 仓储覆盖了 agent 调用但真实仓储实现一度缺失（fake 测试盲区），现已补直测
- mock 模式冒烟：三引擎经共享 runtime 解析正确返回 Mock provider；start → reply ×2 → 会话消息正确累积

## 配置项

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LLM_COACH_WINDOW_SIZE` | 8 | 教练单轮可见的最近消息条数 |
| `LLM_JSON_MODE_ENABLED` | false | 请求 `response_format: json_object`（端点需支持） |

## 遗留与后续批次

- 第三批（体验升级）：文字回复 SSE 流式（需先定文字路径产品定位）、场景分析按 media_id 缓存并经 RQ 异步化
- 独立工程：auth 链路迁 async（同步 psycopg 在热路径）、LLM 滚动摘要兑现 PRD v0.4 会话总结
