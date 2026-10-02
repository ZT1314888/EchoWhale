# EchoWhale 部署运行手册（Runbook）

> 面向单机/小规模生产部署。参考编排：[infra/docker/docker-compose.yml](../infra/docker/docker-compose.yml)（postgres + redis + api + worker）。
> 镜像定义：[infra/docker/Dockerfile](../infra/docker/Dockerfile)（uv --frozen 同步依赖，api 与 RQ worker 共用）。

## 1. 镜像构建

```bash
docker build -f infra/docker/Dockerfile -t echowhale:<tag> .
```

- 依赖同步用 `uv sync --frozen --no-dev`，以 `uv.lock` 为唯一事实源（`requirements.txt` 已于 2026-10-02 移除）。
- CI 的 `docker` job 每次推送都会构建镜像（不推送 registry）；发布推送需接入 registry 凭证，另行配置。

## 2. 环境清单（启动前逐项确认）

应用启动时 `Settings.validate_runtime()` 强制校验生产清单（17 项，缺一即退出并逐项点名）。`APP_ENV` 在白名单 `{development, dev, test, testing, local}` 之外的**一切取值**（含 `prod`/`staging`/空串）都按生产标准校验：

| 类别 | 必填项 |
| --- | --- |
| 认证 | `AUTH_JWT_SECRET`（≥32 字符且非默认值）、`AUTH_COOKIE_SECURE=true`、`ALLOWED_ORIGINS`、`FRONTEND_PUBLIC_BASE_URL` |
| 基础设施 | `DATABASE_URL`（`postgresql+psycopg://...`）、`REDIS_URL` |
| 模型 | `MODEL_RUNTIME_MODE=live`（mock 不允许上线）及 `VISION_PRIMARY_*` / `TEXT_PRIMARY_*` 的 BASE_URL/MODEL |
| 对象存储 | `R2_ENDPOINT` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` |
| 邮件 | `AUTH_SMTP_HOST` / `AUTH_SMTP_USERNAME` / `AUTH_SMTP_PASSWORD` / `AUTH_SMTP_FROM_EMAIL` |
| 语音 | `DEEPGRAM_API_KEY` / `DEEPGRAM_AGENT_BASE_URL` / `DEEPGRAM_AGENT_THINK_MODEL` |

完整键位与语义见 [.env.example](../.env.example)。

## 3. 数据库迁移

- API 容器启动命令内置 `alembic upgrade head`（失败即退出，不产生假就绪）。
- 手动执行：`uv run alembic upgrade head`；回滚：`uv run alembic downgrade <revision>`（迁移均实现 down）。
- 迁移 0011 之前的历史库需先核查 `session_messages` 无重复 `(session_id, position)`（唯一约束会拒绝脏数据）：
  `SELECT session_id, position, count(*) FROM session_messages GROUP BY 1,2 HAVING count(*) > 1;`

## 4. Worker 消费确认

RQ worker 消费 `auth-mail`（注册/重置邮件）与 `scene-analysis`（异步图片分析）两个队列：

- compose 中 `worker` 服务必须与 api 同时在线；`SCENE_ANALYSIS_ASYNC_ENABLED=true` 开启前**必须**确认 worker 正在消费（`rq info` 或看 worker 日志）。
- Redis 缺席时的降级行为：邮件队列任务入队失败、限流退进程内——生产清单已强制 `REDIS_URL`，不应出现。

## 5. 健康与就绪

| 端点 | 语义 | 用途 |
| --- | --- | --- |
| `/health` | liveness：进程活着即 200 | 容器重启判定 |
| `/readyz` | readiness：DB `SELECT 1`、Redis `PING` 实测；R2 仅查配置 | LB/K8s 摘流判定（503 = unready） |

## 6. 反向代理要求

应用**不解析** `X-Forwarded-For`（可伪造）。反代后要让限流按真实客户端 IP 生效，uvicorn 必须以：

```
--proxy-headers --forwarded-allow-ips=<代理IP>
```

启动，使 `request.client.host` 恢复为真实客户端地址。否则所有用户共享代理 IP 的登录/限流桶。

## 7. 回滚

1. 回退镜像 tag（应用无状态，会话数据全在 Postgres）。
2. 需要回退 schema 时：`alembic downgrade` 到目标版本（应用镜像与 schema 版本需匹配——旧镜像配新 schema 兼容性以各迁移 down 注释为准）。
3. 单提交 revert 对应 `git log` 中的 `fix/feat` 提交即可（无数据迁移的提交可直接 revert）。
