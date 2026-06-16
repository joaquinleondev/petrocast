"""Unit tests for the forecast service.

Data comes from the fake connection (canned gold rows: 3 monthly points per
well in 2024-01, 2024-02, 2024-03).
"""

from datetime import date

from src.services.forecast_service import get_forecast
from tests.conftest import _FakeConnection


def test_get_forecast_returns_none_for_unknown_well(fake_conn: _FakeConnection) -> None:
    result = get_forecast(fake_conn, "POZO-999", date(2024, 1, 1), date(2024, 3, 31))
    assert result is None


def test_get_forecast_returns_correct_well_id(fake_conn: _FakeConnection) -> None:
    result = get_forecast(fake_conn, "POZO-001", date(2024, 1, 1), date(2024, 3, 31))
    assert result is not None
    assert result.id_well == "POZO-001"


def test_get_forecast_returns_monthly_points(fake_conn: _FakeConnection) -> None:
    # Canned data has 3 monthly rows for POZO-001 in 2024-01 to 2024-03
    result = get_forecast(fake_conn, "POZO-001", date(2024, 1, 1), date(2024, 3, 31))
    assert result is not None
    assert len(result.data) == 3


def test_get_forecast_production_is_declining(fake_conn: _FakeConnection) -> None:
    result = get_forecast(fake_conn, "POZO-001", date(2024, 1, 1), date(2024, 3, 31))
    assert result is not None
    prods = [p.prod for p in result.data]
    assert prods == sorted(prods, reverse=True)


def test_get_forecast_empty_range_returns_none(fake_conn: _FakeConnection) -> None:
    # Date range outside canned data → no rows → None
    result = get_forecast(fake_conn, "POZO-001", date(2025, 1, 1), date(2025, 12, 31))
    assert result is None
