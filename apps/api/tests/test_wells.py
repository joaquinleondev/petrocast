from fastapi.testclient import TestClient

from app.main import app
from app.mock_data import WELLS

client = TestClient(app)

HEADERS = {"X-API-Key": "abcdef12345"}


def test_get_wells_returns_all_wells():
    response = client.get("/api/v1/wells", params={"date_query": "2024-01-01"}, headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == len(WELLS)


def test_get_wells_response_has_id_well_field():
    response = client.get("/api/v1/wells", params={"date_query": "2024-01-01"}, headers=HEADERS)
    assert response.status_code == 200
    for well in response.json():
        assert "id_well" in well


def test_get_wells_missing_date_query_returns_422():
    response = client.get("/api/v1/wells", headers=HEADERS)
    assert response.status_code == 422
