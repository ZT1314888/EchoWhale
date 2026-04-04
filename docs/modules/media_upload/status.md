# Module Status: `media_upload`

## 基本信息

- `module`: `media_upload`
- `status`: `building`
- `branch`: `module/media_upload`
- `owner`: `unassigned`
- `updated_at`: `2026-04-03`

## 模块目标

负责图片上传、媒体元数据、类型与大小校验、私有对象存储接入，以及为后续场景理解提供稳定的 `storage_key` 和临时读取 URL。

## 当前真相

- 现有实现：`api/models/media_model.py`、`api/db/media_db.py`、`api/integrations/storage/r2.py`、`api/services/media_service.py`、`api/routes/v1/media.py`
- 已完成边界：上传路由、媒体元数据契约、类型/大小/基础文件头校验、session 启动前媒体状态校验、PostgreSQL 持久化底座、统一响应壳
- 当前媒体契约：数据库稳定保存 `storage_key`，接口按需返回短时效 `preview_url` / `read_url`
- session 场景分析读取图片时，已从永久外链切换为签名 URL
- 本地开发态已验证上传接口可返回 `200`、`upload_status=uploaded` 和 HTTPS `preview_url`
- 本地定向回归已跑通：后端 `14 passed`，前端 `8 passed`
- 基础设施目标：R2 改为私有 bucket，Cloudflare 侧重点变为 token、CORS、TLS、限流和密钥轮换
- 当前仍未闭环：真实 Cloudflare R2 私有 bucket 联调、签名读取访问确认、已暴露访问密钥轮换、正式域名与主站同域 `/api` 全链路验证

## 当前进度总结

- `[x]` 上传、查询、access-url 接口已接入 FastAPI 路由树
- `[x]` 上传与查询接口已切到 `code/message/data` 统一响应体
- `[x]` 媒体模型已去掉永久 `public_url` 依赖
- `[x]` session 创建前会拒绝未完成上传的媒体
- `[x]` session 场景分析改为消费签名 URL
- `[x]` media 元数据已切到数据库持久化，并新增迁移移除 `public_url` 列
- `[x]` 前端真实上传主路径已适配新的上传响应契约
- `[x]` 本地开发环境已实际返回成功上传结果，包含 HTTPS `preview_url`
- `[x]` 本地后端与前端定向测试已通过，可证明开发态基础可用
- `[ ]` 还未用真实私有 R2 完成一次端到端上传验证
- `[ ]` 还未确认真实签名读取 URL 的访问结果
- `[ ]` 还未轮换当前已展示过的 R2 访问密钥
- `[ ]` 还未把正式域名、`www` 主站与同域 `/api` 反代纳入模块验收

## 输入输出契约

- 输入：图片文件、文件名、媒体元数据
- 输出：媒体 ID、短时效预览 URL、后续可追踪的媒体记录
- 关键字段：`media_id`、`storage_key`、`upload_status`、`preview_url`、`preview_url_expires_at`

## 代码位置

- `api/models/media_model.py`
- `api/db/database.py`
- `api/db/media_db.py`
- `api/migrations/`
- `api/integrations/storage/`
- `api/services/media_service.py`
- `api/routes/v1/media.py`

## 当前工作

- `[x]` 明确上传接口输入输出
- `[x]` 定义文件校验规则
- `[x]` 补媒体创建、查询与 access-url 的最小测试
- `[x]` 落 PostgreSQL media repository 与 Alembic 迁移
- `[x]` 记录本地开发态上传成功与测试通过的当前证据
- `[ ]` 用真实私有 R2 bucket 做一次联调验证
- `[ ]` 确认真实签名 URL 在有效期内可访问
- `[ ]` 重新生成并替换 R2 Access Key / Secret Access Key

## 测试门

- `module_test_passed` 的标准：上传输入、媒体记录、数据库持久化、签名 URL 生成和 session 读取链路可稳定验证
- 已覆盖：合法文件、非法类型、基础文件头伪装、媒体详情读取、access-url 返回、session 启动前媒体状态约束、session 签名 URL 消费、CSV 配置解析、repository 持久化、本地前端上传契约解包
- 当前证据：本地上传接口返回 `200` 且带 HTTPS `preview_url`；后端 `uv run pytest tests/core/test_config.py tests/db/test_media_repository.py tests/api/test_media_routes.py tests/modules/test_session_engine.py -q` 通过；前端 `npm test -- --run src/services/mediaApi.test.ts src/App.test.tsx` 通过
- 还没覆盖的风险：真实对象存储接入前后的行为差异、Cloudflare 控制台私有 bucket 配置、联调后的密钥轮换操作、正式域名下的主站同域 `/api` 验证

## 阻塞项

- 真实 R2 上传联调尚未执行
- 真实签名读取 URL 访问结果尚未确认
- 当前已展示过访问密钥，联调后应立即轮换
- 整个项目主链路尚未完成，不在当前阶段推进正式域名下的全链路打通结论

## 变更记录

- `2026-03-30`：初始化模块状态文档
- `2026-04-01`：落地 `media` 上传/查询接口、媒体服务、基础图片校验和 session 媒体状态保护
- `2026-04-01`：接入 PostgreSQL/SQLAlchemy/Alembic，媒体元数据改为数据库持久化
- `2026-04-02`：对齐私有 R2 方案，新增签名 URL 返回与 access-url 接口，移除数据库里的永久 `public_url` 契约
- `2026-04-03`：补记本地开发态上传成功、后端 `14 passed` 与前端 `8 passed` 的验证证据；继续保持 `building`，不提前宣称全链路打通
