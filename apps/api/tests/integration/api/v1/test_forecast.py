"""Integration tests for the /forecast endpoint.

Canned gold data (monthly grain):
    POZO-001: 2024-01-01 (150.0), 2024-02-01 (140.0), 2024-03-01 (130.0)
    POZO-002: 2024-01-01 (220.0), 2024-02-01 (210.0), 2024-03-01 (200.0)
    POZO-003: 2024-01-01 (95.0), 2024-02-01 (88.0), 2024-03-01 (81.0)
"""


def test_get_forecast_returns_correct_well_id(client, auth_headers):
    response = client.get(
        "/api/v1/forecast",
        params={"id_well": "POZO-001", "date_start": "2024-01-01", "date_end": "2024-03-31"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["id_well"] == "POZO-001"


def test_get_forecast_returns_monthly_data_points(client, auth_headers):
    # Canned data has 3 monthly rows in 2024-01 to 2024-03
    response = client.get(
        "/api/v1/forecast",
        params={"id_well": "POZO-001", "date_start": "2024-01-01", "date_end": "2024-03-31"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 3
    assert data[0]["date"] == "2024-01-01"
    assert data[-1]["date"] == "2024-03-01"


def test_get_forecast_prod_values_are_declining(client, auth_headers):
    response = client.get(
        "/api/v1/forecast",
        params={"id_well": "POZO-001", "date_start": "2024-01-01", "date_end": "2024-03-31"},
        headers=auth_headers,
    )
    data = response.json()["data"]
    productions = [point["prod"] for point in data]
    assert productions == sorted(productions, reverse=True)


def test_get_forecast_unknown_well_returns_404(client, auth_headers):
    response = client.get(
        "/api/v1/forecast",
        params={"id_well": "POZO-999", "date_start": "2024-01-01", "date_end": "2024-03-31"},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_get_forecast_invalid_date_range_returns_400(client, auth_headers):
    response = client.get(
        "/api/v1/forecast",
        params={"id_well": "POZO-001", "date_start": "2024-01-10", "date_end": "2024-01-01"},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_get_forecast_missing_params_returns_422(client, auth_headers):
    response = client.get("/api/v1/forecast", headers=auth_headers)
    assert response.status_code == 422
