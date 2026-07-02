"""Integration tests for GET /api/v1/predictions (contrato D, F3-17).

The endpoint currently serves the naive-persistence mock; these tests pin
the HTTP contract (params, status codes, response fields) that F3-18/F3-20
must keep intact when swapping in the real model runtime.
"""

from datetime import date

import pytest
from fastapi import HTTPException

from src.core.db import get_connection
from src.main import app

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
    assert body["model_version"] == "naive-persistence-mock"
    assert len(body["predictions"]) == body["horizon"]
    assert all(
        date.fromisoformat(point["month"]) > date.fromisoformat(body["as_of_date"])
        for point in body["predictions"]
    )
    # Naive persistence: last observation at as_of_date is 2024-03 (130.0 m³),
    # repeated over the next `horizon` months.
    assert body["predictions"] == [
        {"month": "2024-04-01", "oil_prod_m3": 130.0},
        {"month": "2024-05-01", "oil_prod_m3": 130.0},
        {"month": "2024-06-01", "oil_prod_m3": 130.0},
    ]


def test_starts_after_as_of_date_when_history_is_older(client, auth_headers):
    resp = client.get(
        URL,
        params={"id_well": "POZO-001", "as_of_date": "2024-06-15", "horizon": 2},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    # The last value comes from March, while output months follow the June cutoff.
    assert body["predictions"] == [
        {"month": "2024-07-01", "oil_prod_m3": 130.0},
        {"month": "2024-08-01", "oil_prod_m3": 130.0},
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


def test_no_history_at_as_of_date_returns_404(client, auth_headers):
    resp = client.get(
        URL,
        params={**VALID_PARAMS, "as_of_date": "2023-12-31"},
        headers=auth_headers,
    )

    assert resp.status_code == 404
    assert "no production history" in resp.json()["detail"]


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
