from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.main import probe_database, probe_r2_config, probe_redis


@pytest.fixture
def client() -> Iterator[TestClient]:
    """隔离 dependency_overrides：只动本文件的探针替身，退出时恢复原状。"""
    saved = dict(app.dependency_overrides)
    yield TestClient(app)
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


def test_readyz_all_green_returns_200(client: TestClient) -> None:
    app.dependency_overrides[probe_database] = lambda: "up"
    app.dependency_overrides[probe_redis] = lambda: "up"
    app.dependency_overrides[probe_r2_config] = lambda: "configured"

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"db": "up", "redis": "up", "r2": "configured"},
    }


def test_readyz_db_down_returns_503(client: TestClient) -> None:
    app.dependency_overrides[probe_database] = lambda: "down"
    app.dependency_overrides[probe_redis] = lambda: "up"
    app.dependency_overrides[probe_r2_config] = lambda: "configured"

    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unready"
    assert body["checks"]["db"] == "down"


def test_readyz_redis_configured_but_down_returns_503(client: TestClient) -> None:
    app.dependency_overrides[probe_database] = lambda: "up"
    app.dependency_overrides[probe_redis] = lambda: "down"
    app.dependency_overrides[probe_r2_config] = lambda: "configured"

    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unready"
    assert body["checks"]["redis"] == "down"


def test_readyz_redis_unconfigured_is_skipped_not_failed(client: TestClient) -> None:
    """开发环境无 REDIS_URL：按未配置跳过，readyz 反映部署契约而非硬失败。"""
    app.dependency_overrides[probe_database] = lambda: "up"
    app.dependency_overrides[probe_redis] = lambda: "unconfigured"
    app.dependency_overrides[probe_r2_config] = lambda: "missing"

    response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["redis"] == "unconfigured"
    # R2 只查配置齐备性：missing 与 redis unconfigured 同一宽容语义，不阻塞 ready。
    assert body["checks"]["r2"] == "missing"


def test_readyz_response_carries_request_id_header(client: TestClient) -> None:
    """探针路径也过 request-id 中间件：基础设施抓取探针响应时能拿到关联 id。"""
    app.dependency_overrides[probe_database] = lambda: "up"
    app.dependency_overrides[probe_redis] = lambda: "unconfigured"
    app.dependency_overrides[probe_r2_config] = lambda: "missing"

    response = client.get("/readyz")

    assert response.headers["x-request-id"].startswith("req_")


def test_readyz_reuses_inbound_request_id(client: TestClient) -> None:
    app.dependency_overrides[probe_database] = lambda: "up"
    app.dependency_overrides[probe_redis] = lambda: "up"
    app.dependency_overrides[probe_r2_config] = lambda: "configured"

    response = client.get("/readyz", headers={"X-Request-ID": "lb-probe-42"})

    assert response.headers["x-request-id"] == "lb-probe-42"


def test_health_route_stays_plain_liveness(client: TestClient) -> None:
    """/health 语义不变：静态 ok，永不因依赖状态返回 503（liveness 归进程）。"""
    app.dependency_overrides[probe_database] = lambda: "down"

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
