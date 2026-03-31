# Features

这个目录记录用户可感知的功能切片。Feature 应该比 module 更接近用户行为，但不要把整条系统链路混在一起。

## 这里放什么

- 图片上传
- 场景识别
- 英语对话生成
- 学习反馈展示
- 会话历史查看

## Feature 的边界

- 一个 feature 只描述一个用户能感知的结果
- 如果它跨多个 engine，就在文档里写清楚依赖关系
- 如果它还没进入实现，只写需求、验收和最小设计，不要写成代码笔记

## 推荐结构

- `feature.md`：该 feature 的定义、范围、验收和测试
- 附件或证据：截图、接口样例、测试记录、原型链接

## 状态词

Feature 状态统一使用：

`planned` -> `in_progress` -> `feature_test_passed` -> `merged_to_module` -> `closed`

## 当前仓库状态

- 目前前端仍是骨架，所以大部分 feature 还应该停留在 `planned`
- 后端已有 scaffold，因此和 `scene_engine`、`coach_engine`、`feedback_engine`、`session_orchestration` 相关的 feature 可以进入 `in_progress`
- 若 feature 影响主链路，必须补测试后再允许合并

## 写作要求

- 说明用户为什么需要这个 feature
- 说明它从哪里开始、到哪里结束
- 说明完成后怎么验证
- 不要把模块内部实现细节写得过重
