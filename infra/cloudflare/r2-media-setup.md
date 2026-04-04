# Cloudflare R2 Media Setup

这份文档只说明 EchoWhale 当前媒体上传链路需要你在 Cloudflare 控制台完成的生产级配置。当前方案已经切到：

- 私有 R2 bucket
- FastAPI 后端中转上传
- 后端签发短时效读取 URL
- 数据库存 `storage_key`，不存永久公开外链

## 当前实现假设

- 对象存储：Cloudflare R2 私有 bucket
- 上传方式：FastAPI 后端中转上传
- 读取方式：后端使用 S3 兼容签名 URL 提供短时效读取地址
- SDK：`boto3` 通过 R2 的 S3 兼容接口上传和签名

## 当前推荐环境划分

- `echowhale-dev-media`
- `echowhale-prod-media`

原因：

- 避免开发联调对象与生产对象混用
- 避免开发 key 误写生产 bucket
- 便于后续分环境轮换 token 和做生命周期规则

## 当前进度快照

- 后端上传接口：`POST /api/v1/media/upload`
- 后端读取地址接口：`GET /api/v1/media/{media_id}/access-url`
- 本地 `.env` 现在需要的关键值：`R2_BUCKET`、`R2_ACCOUNT_ID`、`R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY`、`R2_ENDPOINT`、`R2_SIGNED_URL_TTL_SECONDS`
- 当前下一步：执行一次真实私有 bucket 联调，确认签名 URL 在有效期内可访问
- 安全提醒：之前展示过的 R2 访问密钥应立即轮换

## 1. 创建或确认私有 bucket

在 Cloudflare Dashboard 中：

1. 打开 `R2 Object Storage`
2. 创建 `echowhale-dev-media`
3. 创建 `echowhale-prod-media`
4. 确认两个 bucket 都不依赖公开访问做正式链路

要求：

- 不把 `r2.dev` 作为正式生产读图入口
- 不把用户上传图片长期暴露为公开 bucket

## 2. 创建按环境隔离的 R2 API token

在 Cloudflare Dashboard 中：

1. 打开 `R2 Object Storage`
2. 进入 `Manage R2 API tokens`
3. 为 dev 创建一组 `Object Read & Write` token，只允许 `echowhale-dev-media`
4. 为 prod 创建一组 `Object Read & Write` token，只允许 `echowhale-prod-media`
5. 保存每组 token 的 `Access Key ID` 和 `Secret Access Key`

EchoWhale 需要映射为：

- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_ACCOUNT_ID`
- `R2_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com`

要求：

- 当前已暴露过的 key 立即轮换
- 后续固定 90 天轮换一次
- 不复用 dev token 到 prod

参考：

- `https://developers.cloudflare.com/r2/api/tokens/`
- `https://developers.cloudflare.com/r2/examples/aws/boto3/`

## 3. 配置 bucket CORS

因为前端会在浏览器中直接消费签名读取 URL，bucket 需要最小读取 CORS。

建议配置：

- Allowed origins
  - 正式前端域名
  - `http://localhost:5173`
  - `http://127.0.0.1:5173`
- Allowed methods
  - `GET`
  - `HEAD`
- Allowed headers
  - `*`
- Expose headers
  - `ETag`
- Max age seconds
  - `86400`

参考：

- `https://developers.cloudflare.com/r2/buckets/cors/`

## 4. 配置生命周期规则

建议在 bucket 上增加 lifecycle rules：

- `tmp/` 前缀：1 天后删除
- `test/` 前缀：7 天后删除
- `media/` 前缀：当前业务主数据不自动删除

目的：

- 清理联调和测试垃圾对象
- 避免长期积累无效对象

参考：

- `https://developers.cloudflare.com/r2/buckets/object-lifecycles/`

## 5. 配置 Zone 级 TLS 与安全基线

在 Cloudflare Dashboard 中：

1. 打开 `SSL/TLS`
2. 把 `Minimum TLS Version` 设为 `1.2`
3. 打开 `Always Use HTTPS`
4. 只有在确认主站全链路 HTTPS 稳定后，再启用 `HSTS`

说明：

- 私有 bucket 不要求额外的公开图片子域名
- v1 正式链路不再依赖 `img.030830.xyz`

参考：

- `https://developers.cloudflare.com/ssl/edge-certificates/additional-options/minimum-tls/`

## 6. 配置上传接口限流

限流要配在你的 API 域名上，不是 R2 bucket 上。

推荐：

- 路径：`POST /api/v1/media/upload`
- 阈值：`10 requests / minute / IP`
- 动作：`Managed Challenge`

推荐再补一条：

- 路径：`GET /api/v1/media/*/access-url`
- 阈值：`120 requests / minute / IP`
- 动作：`Block 1 minute`

参考：

- `https://developers.cloudflare.com/waf/rate-limiting-rules/`

## 7. 本地 `.env` 需要填写的值

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/echowhale
R2_BUCKET=echowhale-dev-media
R2_ACCOUNT_ID=你的 Cloudflare account id
R2_ACCESS_KEY_ID=你的 R2 access key id
R2_SECRET_ACCESS_KEY=你的 R2 secret access key
R2_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
R2_SIGNED_URL_TTL_SECONDS=900
MEDIA_MAX_FILE_SIZE=10485760
MEDIA_ALLOWED_CONTENT_TYPES=image/jpeg,image/png,image/webp
```

## 8. 运行方式

安装依赖后，用项目环境启动 API：

```powershell
uv run uvicorn api.main:app --reload
```

上传接口：

```text
POST /api/v1/media/upload
```

签名读取地址接口：

```text
GET /api/v1/media/{media_id}/access-url
```

预期返回示例：

```json
{
  "code": 200,
  "message": "Success",
  "data": {
    "media_id": "med_123456",
    "read_url": "https://<ACCOUNT_ID>.r2.cloudflarestorage.com/...",
    "expires_at": "2026-04-02T12:00:00Z"
  }
}
```

## 9. 当前建议执行顺序

1. 在 Cloudflare 创建私有 dev/prod bucket
2. 创建按 bucket 限权的 dev/prod API token
3. 为 dev bucket 配置最小读取 CORS
4. 在本地 `.env` 填好新的 bucket、token 和 `R2_SIGNED_URL_TTL_SECONDS`
5. 启动后端并从前端触发一次真实上传
6. 记录返回中的 `preview_url`
7. 在有效期内直接访问该 `preview_url`，确认对象可读
8. 调用 `GET /api/v1/media/{media_id}/access-url`，确认可再次获取新的签名 URL
9. 联调完成后立即轮换当前已展示过的 key

## 10. 当前已知限制

- 当前仍是后端中转上传，不是浏览器直传
- 当前还没有完整用户鉴权体系，签名 URL 由后端按 `media_id` 直接签发
- 当前没有真实 Cloudflare 集成测试；剩余验证只包括真实上传、签名读取确认和密钥轮换

## 11. 官方文档

- Cloudflare R2 Tokens
  - `https://developers.cloudflare.com/r2/api/tokens/`
- Cloudflare R2 boto3
  - `https://developers.cloudflare.com/r2/examples/aws/boto3/`
- Cloudflare R2 CORS
  - `https://developers.cloudflare.com/r2/buckets/cors/`
- Cloudflare R2 Lifecycle
  - `https://developers.cloudflare.com/r2/buckets/object-lifecycles/`
- Cloudflare Rate Limiting
  - `https://developers.cloudflare.com/waf/rate-limiting-rules/`
- Cloudflare Minimum TLS
  - `https://developers.cloudflare.com/ssl/edge-certificates/additional-options/minimum-tls/`
