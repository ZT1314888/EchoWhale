# Module Status: `scene_engine`

## 基本信息

- `module`: `scene_engine`
- `status`: `building`
- `branch`: `module/scene_engine`
- `owner`: `unassigned`
- `updated_at`: `2026-04-06`

## 模块目标

根据图片或媒体信息输出场景类型、角色设定、开场白、视觉锚点、教学词汇候选和置信度。

## 当前真相

- 现有实现：`api/modules/scene_engine/` 已支持主模型 / 兜底模型 provider 选择与自动回退
- 已完成边界：schema 归一化、双字段关键词契约、state、agent、service、mock vision provider、OpenAI-compatible vision provider、主备回退逻辑、低置信度与双字段空值质量门、`PNG/JPG/WebP` 质量门、session 显式失败语义
- 当前输出已切到可选 live provider；实测表明主视觉模型可处理项目真实上传后的 R2 签名 URL
- office 类场景提示已补充“接待区 / 等候区 / 访客”一类更贴近口语练习的语境选择，避免默认漂到内部会议语境

## 输入输出契约

- 输入：图片分析输入或媒体上下文
- 输出：场景、角色、开场白、视觉锚点、教学词汇候选、置信度
- 关键字段：`scene`、`role`、`opener`、`visual_anchors`、`vocab_candidates`
- unsupported 输入：抛 `UnsupportedSceneImageError`，错误码 `1007`，默认消息 `Unsupported scene image`

## 代码位置

- `api/modules/scene_engine/`
- 相关 provider：`api/modules/scene_engine/providers/`

## 当前工作

- `[x]` 收敛 provider 契约
- `[x]` 明确异常和兜底输出
- `[x]` 补主备回退的核心 agent 测试
- `[x]` 用真实视觉模型验证项目真实上传图片的签名 URL 路径
- `[x]` 补低置信度、异常结构与双字段空值的 fallback 测试
- `[x]` 把 `session_engine.start()` 的基础设施型 scene 失败从静态兜底切为显式报错
- `[x]` 增加 opt-in live evaluation 骨架与 judge/JSONL 结果记录
- `[x]` 让纯黑/纯白/不可练习图片走 `UnsupportedSceneImageError`
- `[ ]` 准备真实样本清单并跑第一轮 live evaluation

## 测试门

- `module_test_passed` 的标准：
  - 合法输入时输出结构稳定
  - 主模型失败、低置信度或结构异常时能走兜底
  - session 链路在 `scene_engine` 双重失败时仍可静态降级
  - 纯黑/纯白或不可练习图片会以 `422/1007` 失败返回，不再创建 session
  - 已准备 live evaluation 入口，可基于真实签名 URL 做样本评估
- 当前证据：
  - `tests/modules/test_scene_engine.py`
  - `tests/modules/test_scene_engine_evaluation.py`
  - `tests/modules/test_session_engine.py`
- 还没覆盖的风险：
  - 真实视觉模型在复杂图片上的 role/opener 质量波动
  - 视觉兜底模型当前不可用
  - live evaluation 仍需补真实样本文件并执行

## 评估入口

- 说明文档：`docs/modules/scene_engine/evaluation.md`
- live test：`tests/modules/test_scene_engine_live.py`
- 输出日志：默认写到 `tmp/scene_engine_eval/results.jsonl`

## 阻塞项

- 主视觉链路已收紧为更轻的 JSON-only prompt，并把默认视觉模型示例切到更稳的非 thinking VLM

## 变更记录

- `2026-04-06`：细化 office 场景提示与 mock 兜底语义，优先产出更贴近接待 / 访客语境的 role、opener 和 practice vocab
- `2026-04-06`：升级到 `visual_anchors + vocab_candidates` 双字段契约，并重写 evaluation 基线
- `2026-04-06`：补 schema 归一化、低置信度/空标签质量门、session 显式失败语义与 live evaluation 骨架
- `2026-04-06`：新增 unsupported image 契约、`PNG/JPG/WebP` 质量门、`422/1007` session 失败响应与前端 loading 拦截
- `2026-04-05`：接入主备 provider 配置入口与 scene fallback 测试
- `2026-03-30`：初始化模块状态文档


