# 会话启动媒体归属校验（session_media_ownership_check）

> 审计报告（audit-report-EchoWhale-2026-10-01.md）Finding 4 修复。
> Trellis 任务：`.trellis/tasks/10-01-session-start-media-ownership`（轻量，PRD-only）。

## 目标

`SessionEngineAgent.start()` 是全仓唯一没有归属校验的资源入口：加载媒体后仅检查 upload_status，从不比较 `media.user_id` 与发起者。知道他人 media_id 的攻击者可触发对受害者私人图片的视觉分析，并从共享场景缓存读取场景描述（信息泄漏 + 视觉调用成本转嫁 + 缓存投毒）。

## 实现说明

- `start()` 的 media 分支在加载媒体后内联校验 `media.user_id == payload.user_id`，不一致抛 `NotFoundError`（沿用"收敛成 404 防存在性探测"的 `_ensure_owner` 模式）。
- 校验位置有意放在 upload-status 检查、缓存查询与场景分析派发**之前**：跨用户请求连媒体的上传状态都不应探到，更不得命中缓存（缓存按 media_id 共享，命中即泄漏场景描述）或触发视觉调用。
- sample_scene 分支与属主正常路径行为不变；不做"归属下沉到仓储查询条件"的重构（审计 Better fix，另行立项）。

## 验证

- 新增 `test_start_session_rejects_cross_user_media_before_cache_or_analysis`：跨用户 media_id（upload_status=uploaded）→ NotFoundError，且断言场景分析 store 零读写、场景引擎零调用、零签名 URL、零会话落库。做了变异验证：移除校验 → 测试红；恢复 → 绿。
- `uv run pytest tests -q`：387 passed / 2 skipped；ruff / black 全绿。

## 遗留

- 审计 Better fix（`get_media(media_id, owner_id=...)` 仓储级强制归属）待排——可消除"每个调用方自己记得校验"的模式。
