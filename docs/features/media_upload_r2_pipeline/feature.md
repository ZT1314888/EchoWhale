# Feature: `media_upload_r2_pipeline`

## 基本信息

- `feature`: `media_upload_r2_pipeline`
- `status`: `in_progress`
- `branch`: `feature/media_upload/r2-pipeline`
- `module`: `media_upload`
- `cross_module`: `yes`
- `owner`: `unassigned`
- `updated_at`: `2026-04-03`

## 当前进度总结

- 后端上传链路已落地：`POST /api/v1/media/upload`、`GET /api/v1/media/{media_id}`、`GET /api/v1/media/{media_id}/access-url`
- 媒体正式契约已切到私有存储思路：数据库稳定保存 `media_id`、`storage_key`、`upload_status`、`file_size`
- 上传成功时，接口会额外返回短时效 `preview_url` 与 `preview_url_expires_at`
- session 创建前仍会校验媒体必须已上传成功，但场景分析读取图片时已改为按 `storage_key` 临时签发读取 URL
- 前端 loading 页已适配新的上传返回结构，不再依赖永久 `public_url`
- PostgreSQL/Alembic 底座已存在，并已新增迁移移除 `public_url` 列
- 本地开发态已实际验证上传成功，返回 `media_id`、`storage_key`、`upload_status=uploaded` 与 HTTPS `preview_url`
- 本地定向回归已验证：后端 `14 passed`，前端 `8 passed`
- 当前剩余工作：用真实私有 R2 bucket 做一次联调上传、验证签名读取 URL 可访问、在 Cloudflare 控制台完成私有 bucket 生产配置并轮换已暴露密钥；在整个项目主链路打通前不把正式域名同域链路写成已完成

## 背景

EchoWhale 的主链路从“用户上传图片”开始。此前实现把媒体对象设计成永久公开 URL，这对 demo 可用，但不适合生产级用户图片。当前 feature 已把媒体契约收敛为“长期保存 `storage_key`，按需签发短时效读取 URL”，以便后续接入更严格的访问控制。

## 用户故事

- 当我上传一张生活场景图片时，
- 我希望系统立即返回一条稳定媒体记录和一个可短时访问的预览地址，
- 这样我既能继续创建练习会话，也不会把用户图片长期暴露为公开外链。

## 范围

### In scope

- `POST /api/v1/media/upload` 单图上传
- `GET /api/v1/media/{media_id}` 媒体详情读取
- `GET /api/v1/media/{media_id}/access-url` 短时效读取地址签发
- 图片类型、大小和基础文件头校验
- `storage_key`、`upload_status`、`preview_url`、`preview_url_expires_at` 契约落地
- media 元数据 PostgreSQL 持久化与迁移脚本
- session 创建前校验媒体必须已上传成功
- session 场景分析改为消费短时效读取 URL
- Cloudflare R2 私有 bucket 所需环境变量和接入文档

### Out of scope

- 浏览器直传 R2
- 多文件批量上传
- 图片处理变体、压缩和转码
- 完整用户鉴权体系
- Worker 鉴权中转

## 设计要点

- 关键流程：前端传 `multipart/form-data` -> FastAPI 校验图片 -> 生成 `media_id` 与 `storage_key` -> 存储服务上传对象 -> 写库 -> 按 TTL 生成 `preview_url` -> 返回媒体元数据。
- 存储策略：数据库只保存稳定的 `storage_key`，不再把永久公开 URL 作为正式契约。
- 访问策略：前端与场景分析都通过短时效签名 URL 读取私有对象。
- 响应约束：`/api/v1/media/*` 遵循统一响应壳；前端从 `data` 解包成功结果，从 `message` 读取错误信息。
- 失败时如何处理：非法类型返回 `415`，伪装图片内容返回 `400`，超限返回 `413`，对象存储错误返回 `502`。

## 验收标准

- `[x]` 合法的 `jpeg/png/webp` 文件能通过上传接口返回媒体元数据
- `[x]` 上传接口返回短时效 `preview_url` 与 `preview_url_expires_at`
- `[x]` 媒体详情接口能返回不依赖永久外链的稳定契约
- `[x]` access-url 接口能按 `media_id` 返回新的短时效读取 URL
- `[x]` session 创建会拒绝 `upload_status != uploaded` 的媒体
- `[x]` session 场景分析读取图片时使用签名 URL
- `[x]` media 元数据可持久化保存，并通过迁移脚本初始化/升级表结构
- `[x]` 前端选择本地图片后，会在 loading 页调用真实上传接口，并在成功后继续进入练习页
- `[x]` 本地开发环境已能实际返回成功上传结果，且 `preview_url` 为 HTTPS
- `[ ]` 使用真实 Cloudflare R2 凭证完成一次私有 bucket 联调上传
- `[ ]` 确认真实上传后的签名读取 URL 在有效期内可访问
- `[ ]` 联调完成后轮换当前已暴露过的 R2 访问密钥
- `[ ]` 在正式域名和主站同域 `/api` 场景下完成整条上传链路验证

## 测试记录

- 当前本地验证已覆盖：配置解析、repository 持久化、上传/查询/access-url API、session 媒体状态保护、session 签名 URL 消费、前端上传契约解包、本地上传成功返回 HTTPS `preview_url`
- 主要测试命令：
  - `uv run pytest tests/core/test_config.py tests/db/test_media_repository.py tests/api/test_media_routes.py tests/modules/test_session_engine.py -q`
  - `RUN_R2_INTEGRATION=1 uv run pytest tests/integration/test_r2_media_pipeline.py -q`
  - `npm test -- src/services/mediaApi.test.ts src/App.test.tsx`
- 最新本地结果：后端 `14 passed`；前端 `8 passed`
- 已知缺口：真实私有 R2 上传与签名读取联调、Cloudflare 控制台私有 bucket 配置、密钥轮换、正式域名下的同域 `/api` 与主站 HTTPS 闭环

## 合并与关闭

- 真实 R2 联调完成且 Cloudflare 侧配置收口后，才可以写成 `feature_test_passed`
- 在整个项目主链路打通、正式域名与同域 `/api` 完成验证前，不把当前本地上传成功视为 feature 闭环
- 合入 `module/media_upload` 并通过模块级验证后，才可以推进到 `merged_to_module`
- 相关文档链接：
  - `docs/modules/media_upload/status.md`
  - `infra/cloudflare/r2-media-setup.md`
