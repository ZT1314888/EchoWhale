# Version: `2026-04-06-scene-labels-contract-v3`

## 摘要

本轮把 `scene_engine` 的单一 `labels` 契约升级为：

- `visual_anchors`
- `vocab_candidates`

同时同步改造：

- `session_engine` 编排与持久化
- `coach_engine` 输入契约
- `feedback_engine` 输入契约
- `sessions/history` API 返回
- `scene_engine` evaluation 基线与公开样本

## 关键原因

- 旧 `labels` 同时承载“看图线索”和“教学词汇”，导致下游混用
- `table` 这类泛化词会污染对话和反馈
- 旧评估基线对真实视觉输出过于脆弱，也无法衡量教学价值

## 当前状态

- 双字段契约已在后端主链路落地
- 旧 `labels` 仅保留内部兼容聚合语义
- session 数据库已新增新列迁移脚本
- 公开样本不再把 `table` 当成办公室图片的默认正确标签
