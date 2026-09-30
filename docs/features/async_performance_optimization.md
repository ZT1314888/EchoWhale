# 异步性能与并发优化

## 目标

- 修正 `session_engine` 中会返回 coroutine 的异步错误。
- 让会话回复链路中的 feedback / coach 两个外部调用并发执行。
- 把 `scene quality gate` 与 Deepgram think proxy 从同步 HTTP I/O 改为 async 路径。
- 为数据库连接池补充显式容量配置入口，降低后续压测时的隐式瓶颈。

## 本次改动

- `api/modules/session_engine/agent.py`
  - `reply()` 改为 `asyncio.gather(...)` 并发跑 feedback 与 coach。
  - `get_history_session_overview()` 改为正确 `await` 并并发读取 session、review、message count。
- `api/modules/scene_engine/service.py`
  - 质量筛查改为 await async gate。
- `api/modules/scene_engine/tools/image_quality.py`
  - 图片抓取改成 `httpx.AsyncClient`。
  - Pillow 解码与像素扫描下沉到 `asyncio.to_thread(...)`，避免阻塞事件循环。
- `api/routes/v1/deepgram.py`
  - think proxy 改为 shared `httpx.AsyncClient`。
  - SSE 转发改成 async streaming。
- `api/integrations/llm/openai.py`
  - 增加 shared sync/async client 复用，减少每次请求重建连接。
- `api/core/config.py` / `api/db/database.py`
  - 新增数据库池容量参数并接入 engine 构建。
- `.env.example`
  - 补充数据库池配置样例。

## 验证

- 模块级：`tests/modules/test_session_engine.py`
- 模块级：`tests/modules/test_scene_image_quality.py`
- API 级：`tests/api/test_deepgram_routes.py`
- API 级：`tests/api/test_deepgram_routes_async.py`

## 已知未覆盖项

- 上传接口仍是整文件一次性读入内存，尚未改成分块流式上传。
- `session_repository` 的 transcript 重写与部分查询放大问题，这一轮未继续下沉。
- auth 路径仍是同步仓储与进程内频控，没有一起迁到 async / Redis 统一频控。
