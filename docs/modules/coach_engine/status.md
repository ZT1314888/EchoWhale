# Module Status: `coach_engine`

## 基本信息

- `module`: `coach_engine`
- `status`: `building`
- `branch`: `module/coach_engine`
- `owner`: `unassigned`
- `updated_at`: `2026-04-09`

## 模块目标

在给定场景和对话上下文下生成角色一致、可继续追问的英语陪练回复。

## 当前真相

- 现有实现：`api/modules/coach_engine/` 已支持 `visual_anchors + vocab_candidates + recent_messages` 输入契约
- 已完成边界：schema、state、agent、service、chat provider 骨架、OpenAI-compatible 文本 provider、主备回退逻辑
- 已完成边界：live 模式下已收紧 provider 选择语义；当 primary/fallback 都未配置真实文本 provider 时不再静默退回 mock，而是显式报配置错误
- mock 路径已开始把视觉锚点、教学词汇和最近消息带入追问文本，live prompt 也已补上“证据约束下的合理情境扩展”规则

## 输入输出契约

- 输入：场景设定、历史消息、学习者回复、视觉锚点、教学词汇候选
- 输出：教练式回应、下一步交流推进
- 关键字段：`role`、`visual_anchors`、`vocab_candidates`、`recent_messages`、回复文本

## 代码位置

- `api/modules/coach_engine/`
- 相关 provider：`api/modules/coach_engine/providers/`

## 当前工作

- `[x]` 明确多轮上下文最小契约
- `[x]` 补 `visual_anchors / recent_messages` 参与回复的回归测试
- `[x]` 用真实文本模型验证主链路追问可用
- `[x]` 给 live prompt 增加 grounded reply 约束，允许基于图片证据做有限情境推断
- `[ ]` 继续验证多样本下的角色一致性与追问稳定性

## 测试门

- `module_test_passed` 的标准：多轮上下文下回复结构稳定、角色不漂移、可消费视觉锚点与教学词汇，并避免脱离图片证据的剧情漂移
- 当前证据：`tests/modules/test_coach_engine.py` 已覆盖 `visual_anchors / vocab_candidates / recent_messages` 输入、grounded prompt 约束，以及 live 模式下至少存在一个真实文本 provider 的配置门禁
- 还没覆盖的风险：真实 LLM 接入后的风格稳定性差异、文本兜底模型当前不适合结构化 JSON 任务

## 阻塞项

- 主文本模型已完成 live 联调，文本兜底模型仍需更换或继续调试

## 变更记录

- `2026-04-06`：补 `vocab_candidates` 输入，并将 live prompt 收紧为“证据约束 + 有限情境扩展”
- `2026-04-05`：扩展上下文输入契约并接入主备文本 provider
- `2026-04-09`：收紧 live provider 语义，避免在真实运行模式下因空配置静默回落到 mock chat provider
- `2026-03-30`：初始化模块状态文档


