"""Best-effort Arps fitting: recovers synthetic declines, degrades to None."""

import numpy as np
import pandas as pd
import pytest

from petrocast_ml.evaluation.arps import MIN_POSITIVE_POINTS, ArpsFit, fit_well, forecast


def _series(rates: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    months = pd.date_range(start, periods=len(rates), freq="MS")
    return pd.DataFrame({"well_id": "w1", "production_month": months, "oil_prod_m3": rates})


def test_recovers_exponential_decline() -> None:
    # Exponential is the b -> 0 edge of the hyperbolic family.
    t = np.arange(24, dtype=float)
    rates = 500.0 * np.exp(-0.08 * t)
    fit = fit_well(_series(list(rates)))
    assert fit is not None
    future = pd.Series(pd.date_range("2026-01-01", periods=3, freq="MS"))
    expected = 500.0 * np.exp(-0.08 * np.array([24.0, 25.0, 26.0]))
    assert forecast(fit, future) == pytest.approx(expected, rel=0.05)


def test_recovers_hyperbolic_decline() -> None:
    t = np.arange(30, dtype=float)
    rates = 800.0 / np.power(1.0 + 0.6 * 0.09 * t, 1.0 / 0.6)
    fit = fit_well(_series(list(rates), start="2023-07-01"))
    assert fit is not None
    assert fit.b == pytest.approx(0.6, abs=0.15)
    future = pd.Series(pd.date_range("2026-01-01", periods=3, freq="MS"))
    expected = 800.0 / np.power(1.0 + 0.6 * 0.09 * np.array([30.0, 31.0, 32.0]), 1.0 / 0.6)
    assert forecast(fit, future) == pytest.approx(expected, rel=0.05)


def test_zero_months_are_excluded_from_the_fit_but_not_the_clock() -> None:
    # A shut-in month keeps its calendar slot: t counts months since first
    # observation, so the decline clock does not compress around gaps.
    t = np.arange(24, dtype=float)
    rates = list(500.0 * np.exp(-0.08 * t))
    rates[10] = 0.0  # shut-in
    fit = fit_well(_series(rates))
    assert fit is not None
    future = pd.Series(pd.date_range("2026-01-01", periods=1, freq="MS"))
    assert forecast(fit, future) == pytest.approx([500.0 * np.exp(-0.08 * 24.0)], rel=0.08)


def test_too_few_positive_points_returns_none() -> None:
    rates = [0.0] * 10 + [100.0] * (MIN_POSITIVE_POINTS - 1)
    assert fit_well(_series(rates)) is None


def test_all_zero_or_empty_returns_none() -> None:
    assert fit_well(_series([0.0] * 12)) is None
    assert fit_well(_series([])) is None


def test_never_raises_on_unstructured_series() -> None:
    # Increasing production contradicts a decline; best-effort means None or a
    # (bad) fit, never an exception.
    rates = list(np.linspace(10.0, 900.0, 18))
    result = fit_well(_series(rates))
    assert result is None or isinstance(result, ArpsFit)
