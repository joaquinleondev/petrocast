"""Integration tests for GET /api/v1/predictions (contrato D, F3-17).

The endpoint currently serves the naive-persistence mock; these tests pin
the HTTP contract (params, status codes, response fields) that F3-18/F3-20
must keep intact when swapping in the real model runtime.
"""

import pytest

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
    # Naive persistence: last observation at as_of_date is 2024-03 (130.0 m³),
    # repeated over the next `horizon` months.
    assert body["predictions"] == [
        {"month": "2024-04-01", "oil_prod_m3": 130.0},
        {"month": "2024-05-01", "oil_prod_m3": 130.0},
        {"month": "2024-06-01", "oil_prod_m3": 130.0},
    ]


def test_uses_last_observation_at_or_before_as_of_date(client, auth_headers):
    resp = client.get(
        URL,
        params={"id_well": "POZO-001", "as_of_date": "2024-02-10", "horizon": 2},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    # Last observation at 2024-02-10 is 2024-02 (140.0 m³): months after it.
    assert body["predictions"] == [
        {"month": "2024-03-01", "oil_prod_m3": 140.0},
        {"month": "2024-04-01", "oil_prod_m3": 140.0},
    ]


def test_unknown_well_returns_404(client, auth_headers):
    resp = client.get(URL, params={**VALID_PARAMS, "id_well": "NOPE-999"}, headers=auth_headers)

    assert resp.status_code == 404
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
