from src.core import serving


def test_health_live_returns_200_without_auth(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_health_ready_returns_200_without_auth(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_health_deep_requires_api_key(client):
    response = client.get("/health/deep")
    assert response.status_code == 403


def test_health_deep_returns_rich_payload(client, auth_headers):
    response = client.get("/health/deep", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "uptime_seconds" in body
    assert "checks" in body


def test_health_deep_reports_real_model_serving_state(client, auth_headers):
    serving._load_cached_champion.cache_clear()

    response = client.get("/health/deep", headers=auth_headers)

    assert response.status_code == 200
    checks = response.json()["checks"]
    assert "forecast_engine" not in checks
    assert checks["model_serving"]["status"] == "not_loaded"
