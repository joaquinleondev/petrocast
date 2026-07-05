"""Metric semantics of contract F against hand-computed and frozen values."""

import numpy as np
import pandas as pd
import pytest

from petrocast_ml.evaluation.metrics import (
    PREDICTION_COLUMN,
    distribution,
    eligible_wells,
    one_step_naive_mae,
    per_well_metrics,
)
from petrocast_ml.training.dataset import NAIVE_COLUMN, TARGET_COLUMN

CUTOFF = pd.Timestamp("2026-01-01")


def test_eligibility_excludes_wells_under_12_observed_months(
    production_monthly: pd.DataFrame,
) -> None:
    # 70003 is the cold-start well: 5 observed months before the cutoff.
    assert eligible_wells(production_monthly, as_of_date=CUTOFF) == ["70001", "70002", "70004"]


def test_insample_naive_mae_matches_frozen_fixture(
    production_monthly: pd.DataFrame, expected_naive_backtest: pd.DataFrame
) -> None:
    # The F3-10 fixture froze the MASE denominator convention: successive
    # observed rows, calendar gaps collapse (70002 is the well with gaps).
    computed = one_step_naive_mae(production_monthly, as_of_date=CUTOFF)
    expected = expected_naive_backtest.groupby("well_id")["naive_insample_mae_m3"].first()
    for well_id, value in expected.items():
        assert computed[well_id] == pytest.approx(value), well_id


def test_insample_naive_mae_needs_two_observations() -> None:
    production = pd.DataFrame(
        {
            "well_id": ["w1"],
            "production_month": [pd.Timestamp("2025-12-01")],
            "oil_prod_m3": [100.0],
        }
    )
    assert "w1" not in one_step_naive_mae(production, as_of_date=CUTOFF).index


def _test_frame() -> pd.DataFrame:
    # One well, three pooled horizons: errors 1, 2, 3 -> MAE 2; naive errors 2, 2, 2.
    return pd.DataFrame(
        {
            "well_id": ["w1", "w1", "w1"],
            TARGET_COLUMN: [10.0, 20.0, 0.0],
            PREDICTION_COLUMN: [11.0, 18.0, 3.0],
            NAIVE_COLUMN: [12.0, 22.0, 2.0],
        }
    )


def test_per_well_metrics_hand_computed() -> None:
    metrics = per_well_metrics(_test_frame(), insample_naive_mae=pd.Series({"w1": 4.0}))
    row = metrics.loc["w1"]
    assert row["model_mae_m3"] == pytest.approx(2.0)
    assert row["model_rmse_m3"] == pytest.approx(np.sqrt((1 + 4 + 9) / 3))
    assert row["naive_mae_m3"] == pytest.approx(2.0)
    assert row["mase"] == pytest.approx(2.0 / 4.0)
    # MAPE skips the zero-actual row: mean(1/10, 2/20) * 100.
    assert row["mape_nonzero_pct"] == pytest.approx(10.0)


def test_mase_undefined_when_denominator_is_zero_or_missing() -> None:
    frame = _test_frame()
    flat = per_well_metrics(frame, insample_naive_mae=pd.Series({"w1": 0.0}))
    missing = per_well_metrics(frame, insample_naive_mae=pd.Series(dtype=float))
    assert np.isnan(flat.loc["w1", "mase"])
    assert np.isnan(missing.loc["w1", "mase"])


def test_mape_undefined_for_all_zero_actuals() -> None:
    frame = _test_frame()
    frame[TARGET_COLUMN] = 0.0
    metrics = per_well_metrics(frame, insample_naive_mae=pd.Series({"w1": 4.0}))
    assert np.isnan(metrics.loc["w1", "mape_nonzero_pct"])


def test_per_well_metrics_skips_rows_without_naive() -> None:
    frame = _test_frame()
    frame.loc[2, NAIVE_COLUMN] = np.nan
    metrics = per_well_metrics(frame, insample_naive_mae=pd.Series({"w1": 4.0}))
    assert metrics.loc["w1", "model_mae_m3"] == pytest.approx(1.5)


def test_distribution_quantiles_and_empty() -> None:
    values = pd.Series([1.0, 2.0, 3.0, 4.0])
    result = distribution(values)
    assert result == {
        "p50": pytest.approx(2.5),
        "p75": pytest.approx(3.25),
        "p90": pytest.approx(3.7),
    }
    assert distribution(pd.Series(dtype=float)) == {}
    assert distribution(pd.Series([np.nan])) == {}
