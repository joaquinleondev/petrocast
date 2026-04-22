def test_get_forecast_returns_correct_well_id(client, auth_headers):
    response = client.get(
        "/api/v1/forecast",
        params={"id_well": "POZO-001", "date_start": "2024-01-01", "date_end": "2024-01-05"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["id_well"] == "POZO-001"


def test_get_forecast_returns_data_for_each_day_in_range(client, auth_headers):
    response = client.get(
        "/api/v1/forecast",
        params={"id_well": "POZO-001", "date_start": "2024-01-01", "date_end": "2024-01-05"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 5
    assert data[0]["date"] == "2024-01-01"
    assert data[-1]["date"] == "2024-01-05"


def test_get_forecast_prod_values_are_declining(client, auth_headers):
    response = client.get(
        "/api/v1/forecast",
        params={"id_well": "POZO-001", "date_start": "2024-01-01", "date_end": "2024-01-10"},
        headers=auth_headers,
    )
    data = response.json()["data"]
    productions = [point["prod"] for point in data]
    assert productions == sorted(productions, reverse=True)


def test_get_forecast_unknown_well_returns_404(client, auth_headers):
    response = client.get(
        "/api/v1/forecast",
        params={"id_well": "POZO-999", "date_start": "2024-01-01", "date_end": "2024-01-05"},
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
