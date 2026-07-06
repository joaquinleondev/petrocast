"""Integration tests for GET /api/v1/predictions (contrato D, F3-18).

The endpoint now serves the champion runtime (F3-18): tests run against a
deterministic champion double (``horizon * 100``) and a fake feature store
(conftest). They pin the HTTP contract frozen by F3-17 (params, status codes,
response fields) plus the real error paths (unknown well, missing features,
model/warehouse unavailable).
"""

from datetime import date

import pytest
from fastapi import HTTPException

from src.core.db import get_connection
from src.core.serving import get_champion
from src.main import app
from tests.conftest import FAKE_MODEL_VERSION

URL = "/api/v1/predictions"

VALID_PARAMS = {"id_well": "POZO-001", "as_of_date": "2024-03-15", "horizon": 3}


def test_returns_prediction_with_contract_fields(client, auth_headers):
    resp = client.get(URL, params=VALID_PARAMS, headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"id_well", "as_of_date", "horizon", "model_version", "predictions"}
    assert body["id_well"] == "POZO-001"
    assert body["as_of_date"] == "2024-03-15"
    assert body["horizon"] == 3
    # Audits the concrete champion version that answered (not a mock literal).
    assert body["model_version"] == FAKE_MODEL_VERSION
    assert len(body["predictions"]) == body["horizon"]
    assert all(
        date.fromisoformat(point["month"]) > date.fromisoformat(body["as_of_date"])
        for point in body["predictions"]
    )
    # Champion double predicts horizon * 100 over months following the cutoff.
    assert body["predictions"] == [
        {"month": "2024-04-01", "oil_prod_m3": 100.0},
        {"month": "2024-05-01", "oil_prod_m3": 200.0},
        {"month": "2024-06-01", "oil_prod_m3": 300.0},
    ]


def test_prediction_months_cross_year_boundary(client, auth_headers):
    resp = client.get(
        URL,
        params={"id_well": "POZO-001", "as_of_date": "2024-12-31", "horizon": 2},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    assert [point["month"] for point in resp.json()["predictions"]] == [
        "2025-01-01",
        "2025-02-01",
    ]


def test_unknown_well_returns_404(client, auth_headers):
    resp = client.get(URL, params={**VALID_PARAMS, "id_well": "NOPE-999"}, headers=auth_headers)

    assert resp.status_code == 404
    assert set(resp.json()) == {"detail"}
    assert "NOPE-999" in resp.json()["detail"]


def test_well_without_persisted_features_returns_404(client, auth_headers):
    # POZO-003 exists in dim_well but has no feature row in the store.
    resp = client.get(URL, params={**VALID_PARAMS, "id_well": "POZO-003"}, headers=auth_headers)

    assert resp.status_code == 404
    assert "no persisted features" in resp.json()["detail"]


@pytest.mark.parametrize("horizon", [0, 13, -1])
def test_horizon_out_of_range_returns_422(client, auth_headers, horizon):
    resp = client.get(URL, params={**VALID_PARAMS, "horizon": horizon}, headers=auth_headers)

    assert resp.status_code == 422
    assert set(resp.json()) == {"detail"}
    assert isinstance(resp.json()["detail"], list)


def test_invalid_as_of_date_returns_422(client, auth_headers):
    resp = client.get(
        URL,
        params={**VALID_PARAMS, "as_of_date": "not-a-date"},
        headers=auth_headers,
    )

    assert resp.status_code == 422


def test_missing_api_key_returns_403(client):
    resp = client.get(URL, params=VALID_PARAMS)

    assert resp.status_code == 403
    assert resp.json() == {"detail": "Forbidden"}


def test_unavailable_data_warehouse_returns_503(client, auth_headers, monkeypatch):
    def unavailable_connection() -> None:
        raise HTTPException(
            status_code=503,
            detail="Data warehouse is unavailable. Try again later.",
        )

    monkeypatch.setitem(app.dependency_overrides, get_connection, unavailable_connection)

    resp = client.get(URL, params=VALID_PARAMS, headers=auth_headers)

    assert resp.status_code == 503
    assert resp.json() == {"detail": "Data warehouse is unavailable. Try again later."}


def test_unavailable_model_registry_returns_503(client, auth_headers, monkeypatch):
    def unavailable_champion() -> None:
        raise HTTPException(
            status_code=503,
            detail="Model registry is unavailable. Try again later.",
        )

    monkeypatch.setitem(app.dependency_overrides, get_champion, unavailable_champion)

    resp = client.get(URL, params=VALID_PARAMS, headers=auth_headers)

    assert resp.status_code == 503
    assert resp.json() == {"detail": "Model registry is unavailable. Try again later."}
