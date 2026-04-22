from src.repositories.well_repository import get_all


def test_get_wells_returns_all_wells(client, auth_headers):
    response = client.get(
        "/api/v1/wells", params={"date_query": "2024-01-01"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert len(response.json()) == len(get_all())


def test_get_wells_response_has_id_well_field(client, auth_headers):
    response = client.get(
        "/api/v1/wells", params={"date_query": "2024-01-01"}, headers=auth_headers
    )
    assert response.status_code == 200
    for well in response.json():
        assert "id_well" in well


def test_get_wells_missing_date_query_returns_422(client, auth_headers):
    response = client.get("/api/v1/wells", headers=auth_headers)
    assert response.status_code == 422
