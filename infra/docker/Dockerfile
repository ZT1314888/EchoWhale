# EchoWhale API / RQ worker 共用镜像。
# 基于 uv 官方镜像做依赖同步（--frozen 锁定 uv.lock），单阶段即可：
# 运行时依赖（psycopg[binary]/pillow 等均有 wheel）不需要编译工具链。
FROM python:3.12-slim

# uv 版本锁定而非 latest：镜像构建可复现（audit Release 维度：供应链可复现性）。
COPY --from=ghcr.io/astral-sh/uv:0.9.3 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    # 项目以 --no-install-project 方式不装进 venv（无 build-system），靠 /app
    # 目录导入；显式 PYTHONPATH 不依赖 uvicorn/-m 对 cwd 的隐式行为。
    PYTHONPATH=/app

# 先只拷依赖清单再 sync：pyproject/uv.lock 不变时命中 Docker 层缓存，
# 代码改动不触发重新解析/下载依赖。
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY api ./api
COPY alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

# 默认启动 API；RQ worker 用同一镜像以 command 覆盖启动
# （docker compose 里 worker 服务：python -m api.tasks.worker）。
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
