from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

VALID_KEY = "abcdef12345"


def test_request_without_api_key_returns_403():
    response = client.get("/api/v1/wells", params={"date_query": "2024-01-01"})
    assert response.status_code == 403


def test_request_with_wrong_api_key_returns_403():
    response = client.get(
        "/api/v1/wells",
        params={"date_query": "2024-01-01"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403


def test_request_with_valid_api_key_returns_200():
    response = client.get(
        "/api/v1/wells",
        params={"date_query": "2024-01-01"},
        headers={"X-API-Key": VALID_KEY},
    )
    assert response.status_code == 200
