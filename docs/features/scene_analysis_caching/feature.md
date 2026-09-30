# Feature: `scene_analysis_caching`

## 基本信息

- `feature`: `scene_analysis_caching`
- `status`: `feature_test_passed`
- `module`: `scene_engine`
- `cross_module`: `yes`（session_orchestration 的 start() 消费缓存、infra_delivery 的 RQ 队列）
- `owner`: `lucky`
- `updated_at`: `2026-09-30`
- `merge_target`: `module/scene_engine`

## 背景

session start 的 media 路径每次都内联执行完整场景分析：签发 R2 读 URL → 全图下载 → PIL 逐像素质量筛查 → 视觉 LLM。同一个 media 每次开课都把这条 60 秒预算的链路重付一遍；换一张图重试时同样全价。

## 用户故事

- 当我用同一张照片再次开课，我希望直接进对话，不再等第二次视觉分析。
- 当网络不畅导致分析排队，我希望拿到明确的状态（202 + 可轮询端点），而不是一个挂着 60 秒的请求。
- 当 Redis/RQ 暂时缺席，我希望系统自动退回内联分析，而不是开课直接 500。

## 范围

### In scope

- 新表 `scene_analyses`（media 主键，FK → media.id CASCADE）：`status`（pending/ready/failed）、`prompt_version`、`scene/role/opener/visual_anchors/vocab_candidates/confidence`、`error_code`
- `api/db/scene_analysis_db.py`：`SceneAnalysisStore` 协议 + `SqlAlchemySceneAnalysisStore`（get / save_pending / save_result / save_failure，upsert 单行幂等）+ `SceneAnalysisSnapshot`
- Alembic 迁移 `20260930_0010_create_scene_analyses_table.py`（down_revision=0009），ORM 同步注册进 `create_all_tables(_async)` 双轨
- `start()` 三级分流：缓存命中（status=ready 且 prompt_version 一致）→ 直接用缓存结果建会话（不签 URL、不下载、不调视觉）；未命中且 live+异步开关开 → `save_pending` 后投递 RQ，返回 `SceneAnalysisPending`（路由转 202 + `SessionStartPendingResponse`）；其余情况内联分析并写穿缓存
- Redis/RQ 缺席降级：`enqueue_scene_analysis` 捕获 `ConfigurationError` / `QueuePublishError` 记 warning 并返回 False，调用方降级内联（同时落 failed 行供状态端点追溯），参考 `llm_rate_limit.py` 的降级写法
- mock 模式直返：不排队；内联 mock 分析照常写穿缓存，保证二次开课命中
- RQ 任务：`api/tasks/image_analysis.py` 落实 `enqueue_scene_analysis` + `run_scene_analysis_task`（worker 内自建事件循环与引擎；业务性 UnsupportedSceneImageError 直接记 1007 不重试，其余失败记 1005 后上抛交给 RQ Retry(max=3)）
- worker 队列扩展：`Worker([auth-mail, scene-analysis])`
- 状态端点 `GET /media/{id}/scene-analysis`：unknown/pending/ready/failed + 归属校验（越权收敛 404）
- 配置：`SCENE_ANALYSIS_CACHE_ENABLED`（默认 false，生产 .env 开启）、`SCENE_ANALYSIS_ASYNC_ENABLED`（默认 false，前端轮询接线后开启）、`SCENE_ANALYSIS_PROMPT_VERSION`（bump 即整体失效重建）、`SCENE_ANALYSIS_QUEUE_NAME`

### Out of scope

- 前端轮询/等待页接线（下一批随文字路径 UI 一起做）
- 失败结果的负缓存（failed 行只作追溯，重试 start 会重新入队）
- 跨 prompt 版本的多版本缓存共存（单行覆盖式）

## 语义决策

- 缓存命中跳过的不只是视觉调用，还包括质量门禁与低置信度业务门禁——门禁结论本身就是缓存值的一部分（ready 行必然通过了全部门禁）
- 损坏的缓存行（关键字段缺失）在读取时降级视为未命中并告警，下一次 start 重分析覆写，自愈
- 入队成功后 worker 完成与 `save_pending` 落库之间存在窗口竞态，采用"last write wins + 任务幂等"接受极小概率的重复分析，避免引入分布式锁复杂度

## 测试

- `tests/db/test_scene_analysis_store.py`：真仓储直测（pending→ready→failed 往返、upsert 单行、media 删除级联、版本字段）
- `tests/modules/test_scene_cache.py`：命中不签 URL 不调视觉、版本失效重分析、内联写穿后二次命中（验收指标）、live+异步入队返回 Pending 且不建会话、入队失败降级内联、样例场景入口完全旁路
- `tests/api/test_scene_status_route.py`：ready/pending/failed/unknown 载荷、缺失与越权 404
- `tests/integration/test_mock_smoke.py`：真实 HTTP 下两次开课，质量门禁与签名调用次数保持 1 次
