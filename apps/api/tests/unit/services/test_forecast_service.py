from datetime import date

from src.services.forecast_service import get_forecast


def test_get_forecast_returns_none_for_unknown_well():
    result = get_forecast("POZO-999", date(2024, 1, 1), date(2024, 1, 5))
    assert result is None


def test_get_forecast_returns_correct_well_id():
    result = get_forecast("POZO-001", date(2024, 1, 1), date(2024, 1, 5))
    assert result is not None
    assert result.id_well == "POZO-001"


def test_get_forecast_returns_one_point_per_day():
    result = get_forecast("POZO-001", date(2024, 1, 1), date(2024, 1, 5))
    assert result is not None
    assert len(result.data) == 5


def test_get_forecast_production_is_declining():
    result = get_forecast("POZO-001", date(2024, 1, 1), date(2024, 1, 10))
    assert result is not None
    prods = [p.prod for p in result.data]
    assert prods == sorted(prods, reverse=True)
