# Feature: `media_upload_stream_guard`

## 基本信息

- `feature`: `media_upload_stream_guard`
- `module`: `media_upload`（上传链路内存有界化）
- `cross_module`: `yes`（platform_foundation 新增全局请求体中间件；session_orchestration 路由改用公共限流 helper）
- `status`: `feature_test_passed`
- `updated_at`: `2026-10-01`

## 目标

修复全量审计报告（`audit-report-EchoWhale-2026-10-01.md`）Finding 2：`POST /media/upload` 先把整个 multipart 请求体读进内存（`await file.read()`）才校验 10MB 上限，且端点无限流、匿名可用——单请求内存耗尽 DoS 与 R2 存储成本滥用双通道。本批次交付"内存有界的流式上传链路 + 全局请求体大小门 + 有配额的上传端点"。

## 全局请求体大小门（api/common/middleware.py）

- 新增纯 ASGI `BodySizeLimitMiddleware`：不用 `BaseHTTPMiddleware`（它会先把整个请求体缓冲进内存才放行下游，与防护目标背道而驰）
- 头部声明 `Content-Length` 且超上限：不读 body、不进下游 app，直接回 413 统一信封（下游 handler 完全不执行，测试打点断言）
- 无 `Content-Length`（chunked）：包装 `receive` 逐块计数，超限先发 413 再停止向下游转发剩余 chunk——宁可让下游 multipart 解析因截断失败，也不把超限 body 全部读完
- 双响应防护：`tracking_send` 记录响应是否已开始，已开始（流式场景）则跳过 413 只断流；哨兵异常 `_BodySizeExceeded` 被 `contextlib.suppress` 拦在中间件内，不逃逸成 500
- 413 响应体复用 `ApiResponse.failed(message, body_code=FileTooLargeError.code, http_code=413)` 的序列化形态，与全局异常处理器信封完全一致
- 非法 `Content-Length` 不拦截，按无声明处理走流式计数路径（框架解析层报错）
- 仅处理 `http` scope，lifespan / websocket 直通；SSE（reply/stream）响应逐块原样转发，小 body 请求完全不受影响
- 挂载顺序：先挂 body 门再挂 CORS（Starlette 后添加者在最外层）→ 超限 413 经 CORS 包裹带上跨域头，浏览器前端能读到统一信封

## 上传链路流式化（api/services/media_service.py + api/integrations/storage/r2.py）

- `MediaService.upload_media` 从 `content: bytes` 改为 `fileobj: BinaryIO`：`_validate_and_measure` 在 `asyncio.to_thread` 内按 64KB 分块计数，超限立即抛 `FileTooLargeError` 并停止读取（超限路径不 seek，剩余输入不消费；磁盘 spool 交由 Starlette 的 UploadFile 生命周期清理）
- 魔法字节校验只读首块前 12 字节（JPEG/PNG/WEBP 均可判定，webp 检查 8:12 字节）；空 body 头校验必然失败，与旧 bytes 路径语义一致
- 校验通过后 `fileobj.seek(0)` 再交给 storage——上传调用方收到的是指针归零的完整文件
- `StorageService` Protocol 由 `async_upload_bytes(content)` 换成 `async_upload_fileobj(fileobj)`；R2 实现用 boto3 `upload_fileobj`（ExtraArgs 带 ContentType，磁盘 spool → 网络直传，全程不进进程内存，multipart 自动分片）；旧 bytes 路径已删除（grep 零残留）
- 路由层传 `file.file`（SpooledTemporaryFile，>1MB 已落盘），不再 `.read()`；API 契约不变（仍返回 `MediaResponse`）

## 上传端点限流（api/services/llm_rate_limit.py + api/routes/v1/media.py）

- 新增 action `media_upload`（默认 20 次/小时）与 `media_upload_ip`（匿名对端 IP 兜底，默认 100 次/小时），窗口复用 3600 秒语义
- 抽公共 helper `consume_with_ip_guard(limiter, *, action, ip_action, owner, request)`：先消耗 owner 键，匿名 owner 再追加 `ip:{request.client.host}` 兜底键；不读 XFF（可伪造）；`request.client` 为 None 跳过
- sessions 三个端点（start / reply / reply-stream）改调同一 helper，删除本地 `_consume_anonymous_ip_quota` 重复实现，键顺序与跳过条件不再可能漂移（行为不变，既有用例全绿）
- 限流在进流式校验前消耗：无鉴权门槛的高成本端点先付配额再干活，429 语义与 sessions 一致（code 1006）

## 配置项

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `MAX_REQUEST_BODY_BYTES` | 12582912 | 全局请求体上限（12MB = 10MB 媒体 + multipart 编码余量）；新增更大 body 端点时需同步上调 |
| `MEDIA_UPLOAD_LIMIT` | 20 | 每身份（账号/visitor）每小时上传次数 |
| `MEDIA_UPLOAD_IP_LIMIT` | 100 | 匿名访客每对端 IP 每小时上传兜底上限 |

## 权衡记录

- **先发 413 再停止转发**：无 Content-Length 且超限的极少数场景，客户端偶发看到连接重置也优先保证"超限 body 不读进内存"；有 Content-Length 时（httpx/浏览器默认）响应是确定的
- **upload_fileobj vs put_object**：multipart 多 1-2 个 RTT，换内存 O(1)——审计 Finding 2 的核心诉求优先
- **12MB 全局上限是当前业务最大合法 body + 余量**：未来新增大 body 端点需同步调整（配置注释已写明）
- **不改动 R2 预签名直传方案**（审计报告 Better long-term fix，另行立项）；不涉及媒体元数据模型与迁移、无新依赖，回滚 = revert 单提交

## 测试与验证

- 全量门禁：`uv run pytest tests` **267 passed, 2 skipped**；`uv run ruff check api tests tools` All checks passed；`uv run black --check api tests tools` 116 files unchanged
- 新增 `tests/common/test_middleware.py`：超限 Content-Length 拒绝且下游不执行（打点断言）、cap 内透传、chunked 超限截断 413、chunked cap 内透传、lifespan 直通、非法 Content-Length 回落流式路径、真实 app 栈 413 信封可解析
- 新增 `tests/services/test_media_service.py`：超限即断（storage 零调用 + `TrackingBytesIO` 断言读取停在超限块边界）、三格式头校验通过且 storage 收到 seek(0) 后完整内容、头不匹配/空 body 拒绝
- `tests/api/test_media_routes.py`：fakes 迁移到 fileobj 契约；追加 owner 限额 429、匿名轮换 Cookie 同 IP 超 IP 限额 429、认证用户不受 IP 键影响
- `tests/integration/test_r2_media_pipeline.py`（RUN_R2_INTEGRATION 门控）：真实磁盘临时文件走 `upload_fileobj`，断言 `file_size` 一致
- 注意：`.gitignore` 对 `tests/*` 有忽略规则，本批次两个新测试文件需 `git add -f` 才能入库（既有惯例同 tests/api 等目录）

## 遗留与后续批次

- R2 预签名直传（浏览器直传绕过后端内存与带宽）另行立项
- 审计 Finding 4：`AUTH_JWT_SECRET` 密钥分离
- 审计 Finding 5：auth 限流的反代头处理
