# 请求关联 ID 与就绪探针（request_id_and_readiness）

> 审计报告（audit-report-EchoWhale-2026-10-01.md）Finding 15 最小集修复。
> Trellis 任务：`.trellis/tasks/10-02-request-id-and-readiness`。

## 目标

全仓日志无请求关联 ID（多轮链路横跨反馈+教练+流式+落库，报障无法串日志）；`/health` 只返回静态 ok，基础设施无从判断真实就绪。

## 实现说明

### 1. request-id（api/common/request_context.py + middleware.py）

- `RequestContextMiddleware`（纯 ASGI，管线最内层）：入站 `X-Request-ID` 合法（非空、≤64 可打印 ASCII）则复用，否则生成 `req_<16hex>`；id 入 ContextVar（异步多轮链路中 request 对象够不着的层是 ContextVar 存在的唯一理由）；send 包装器在 `http.response.start` 上回写响应头（SSE 开流前发头，同样生效）；请求结束复位 ContextVar，防 id 泄漏到同线程后续日志。
- `RequestIdFilter` 挂 root logger 全部 handler（幂等）：Logger 级 filter 会被子 logger 传播绕过，handler 级才对全仓生效；root 无 handler 时补带 `[%(request_id)s]` 的 basicConfig，已有 handler（uvicorn 托管）时只追加 filter 不动别人的格式串。
- 有意取舍：body 门 413 拒绝发生在 request-id 上下文建立之前（管线顺序 CORS → body 门 → request-id → 路由），413 响应不带 X-Request-ID，属可接受盲区（已在 main.py 注释）。

### 2. /readyz 就绪探针（main.py）

- 三探针依赖注入（测试用 dependency_overrides 替身，零真实网络）：
  - DB：`SELECT 1` 实测，失败即 down；
  - Redis：未配置 → unconfigured（开发宽容，生产清单已强制）；配置了 → PING 实测，自带 2s 硬超时（探针挂起比探针失败更糟）；
  - R2：只查配置齐备性、零网络（真实探测会产生 S3 费用与慢超时）。
- 判定：只有实测失败（down）才算 unready → 503；unconfigured/missing 是"未部署"而非"坏了"。响应为轻量 JSON（消费方是 LB/K8s，不走 ApiResponse 信封）；每次实时探测无缓存。
- `/health` 保持 liveness 语义不动。

## 验证

- +27 个测试（累计 456 passed / 2 skipped）：入站 id 复用/拒绝矩阵（超长/控制字符/重复头）、响应头回写（含裸 ASGI 响应）、contextvar 下游可见与请求后复位、lifespan 直通、filter 占位与注入、readyz 全绿/db 挂/Redis 挂/未配置矩阵、/health 语义不变。
- ruff / black 全绿。

## 遗留

- uvicorn 自有 access/error 日志不带 request id（应用日志已足够关联请求生命周期）；结构化 JSON 日志开关、OTel/Langfuse 接入、usage 表 owner/session 归因（用 ContextVar 贯穿）归后续批次。
