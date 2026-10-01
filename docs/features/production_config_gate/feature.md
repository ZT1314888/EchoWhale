# 生产配置门控反转与清单补全（production_config_gate）

> 审计报告（audit-report-EchoWhale-2026-10-01.md）Finding 3 修复 + Finding 18 最小修复部分。
> Trellis 任务：`.trellis/tasks/10-01-production-config-gate`。

## 目标

`Settings.validate_runtime()` 原先仅在 `APP_ENV == "production"` 精确匹配时执行生产检查——任何拼写偏差（`prod`/`staging`/`live`/空串）都会带着公开默认 JWT 密钥启动（可伪造任意用户 token），且生产清单遗漏 REDIS_URL、MODEL_RUNTIME_MODE、R2 凭证、DATABASE_URL 与 SMTP。本特性把门控改为 fail-closed 并补全清单，使"忘了声明生产环境"从静默事故变成启动失败。

## 实现说明

### 1. 门控反转

- `NON_PRODUCTION_ENVS = {"development", "dev", "test", "testing", "local"}`（frozenset，大小写不敏感、先 strip）。白名单外的一切取值——包括 `production`、`prod`、空字符串、`localhost`、拼写错误——一律按生产标准校验。
- 空串不豁免：环境变量未注入（compose 漏配）是最常见的生产事故形态，按最严格标准校验属于宁可误报不漏报。
- `localhost` 不进白名单：向 `APP_ENV=localhost` 部署会得到逐项点名的失败清单而非静默豁免，符合 fail-closed 原则。

### 2. 生产清单（17 项聚合报错）

既有项保持：JWT 非默认值、AUTH_COOKIE_SECURE、ALLOWED_ORIGINS、FRONTEND_PUBLIC_BASE_URL、DEEPGRAM 三项。新增：

| 检查项 | 理由 |
| --- | --- |
| AUTH_JWT_SECRET ≥ 32 字符且非默认 | 只挡默认值挡不住 `secret` 这类弱密钥 |
| DATABASE_URL 非空 | 首次请求才暴露缺失 → 启动即拦截 |
| REDIS_URL 非空 | 缺失时验证码/限流静默降级进程内实现，多 worker 必坏 |
| MODEL_RUNTIME_MODE = live | mock 上线即静默假模型，教育产品最恶劣故障 |
| R2_ENDPOINT / ACCESS_KEY_ID / SECRET_ACCESS_KEY | 首次上传才暴露 → 启动即拦截 |
| SMTP 四字段全配 | 注册→激活硬依赖邮件，漏配即全量注册无声瘫痪（Finding 18 最小修复） |

所有缺失项聚合进一条 ConfigurationError（一次点名全部问题），校验通过后打一行非敏感生效模式日志（app_env / model_runtime_mode / scene_analysis_cache）。

### 3. 配置卫生

- 删除死配置字段 `llm_provider`（代码从不读取）及 .env.example 条目；`Settings(extra="ignore")` 保证遗留 env 文件仍可启动。

## 权衡记录

- MODEL_RUNTIME_MODE 生产强制 `live` 而非警告：mock provider 返回固定模板对话，静默上线等于产品失效且不可察觉。
- SMTP 半配置仍由既有 `_validate_smtp_settings` 先行拦截（报"启用时必须设置"），全缺失由生产清单拦截——两道门合围 Finding 18 的静默故障。
- 验证码在 RQ payload 中的哈希化（Finding 18 的 Better fix）不在本特性范围。
- CI 不受影响：ci.yml 未设 APP_ENV → 默认 development → 豁免路径。

## 验证

- `uv run pytest tests -q`：386 passed / 2 skipped（新增 119 个用例：6 生产别名 × 18 缺失项 = 108 fail-closed 参数化、5 豁免、弱密钥边界、mock 上线、caplog 日志脱敏断言）。
- `uv run ruff check api tests tools`：All checks passed；`uv run black --check api tests tools`：116 files unchanged。
- 冒烟：默认 env `/health` 200；`APP_ENV=prod python -c "import api.main"` 启动失败并逐项列出缺失配置。
- `uv run python -m tools.agent_ops check` / `render`：通过。

## 遗留

- Finding 18 的队列 payload 验证码哈希化待排。
- 部署文档（runbook）应记录生产清单为部署契约——归入审计 Release 项的 Dockerfile/runbook 批次。
