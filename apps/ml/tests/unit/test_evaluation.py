"""End-to-end evaluate(): gates pass/fail with stub models on the fixtures."""

import json
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import pytest
from numpy.typing import NDArray

from petrocast_ml.evaluation import EvaluationReport, evaluate
from petrocast_ml.training import TARGET_COLUMN, TrainingRequest, build_training_dataset


@dataclass
class StubModel:
    """Returns preset predictions positionally; evaluate() must not re-order."""

    predictions: NDArray[np.float64]

    def fit(self, features: pd.DataFrame, target: pd.Series) -> "StubModel":
        return self

    def predict(self, features: pd.DataFrame) -> NDArray[np.float64]:
        assert len(features) == len(self.predictions)
        return self.predictions


@pytest.fixture
def dataset(production_monthly: pd.DataFrame, well_features: pd.DataFrame) -> pd.DataFrame:
    return build_training_dataset(well_features, production_monthly, horizons=(1, 2, 3))


@pytest.fixture
def request_eval() -> TrainingRequest:
    return TrainingRequest(as_of_date=date(2026, 1, 1), features_version="fixtures", horizon=3)


def _test_targets(dataset: pd.DataFrame) -> NDArray[np.float64]:
    test = dataset.loc[dataset["as_of_date"] == pd.Timestamp("2026-01-01")]
    return test[TARGET_COLUMN].to_numpy(dtype=np.float64)


def test_perfect_model_passes_gates(
    dataset: pd.DataFrame, production_monthly: pd.DataFrame, request_eval: TrainingRequest
) -> None:
    report = evaluate(
        StubModel(_test_targets(dataset)), dataset, production_monthly, request=request_eval
    )
    assert report.gates_passed
    assert report.wells_in_test == 4
    assert report.wells_eligible == 3  # 70003 filtered: 5 observed months < 12
    assert report.wells_excluded_short_history == 1
    assert report.model_mae_m3 == pytest.approx(0.0)
    assert report.arps_fitted_wells + report.arps_failed_wells == 3
    assert json.loads(json.dumps(report.to_dict()))  # JSON-safe end to end


def test_terrible_model_fails_both_blocking_gates(
    dataset: pd.DataFrame, production_monthly: pd.DataFrame, request_eval: TrainingRequest
) -> None:
    report = evaluate(
        StubModel(_test_targets(dataset) + 10_000.0),
        dataset,
        production_monthly,
        request=request_eval,
    )
    assert not report.gates_passed
    blocking = [gate for gate in report.gates if gate.blocking]
    assert all(gate.passed is False for gate in blocking)


def test_no_eligible_wells_raises(
    dataset: pd.DataFrame, production_monthly: pd.DataFrame, request_eval: TrainingRequest
) -> None:
    # Truncate history to 3 months per well: nobody reaches 12 observed months.
    truncated = (
        production_monthly.sort_values("production_month")
        .groupby("well_id")
        .tail(3)
        .reset_index(drop=True)
    )
    test_rows = int((dataset["as_of_date"] == pd.Timestamp("2026-01-01")).sum())
    with pytest.raises(ValueError, match="eligible"):
        evaluate(StubModel(np.zeros(test_rows)), dataset, truncated, request=request_eval)


def test_raises_when_mase_defined_for_too_few_wells(
    dataset: pd.DataFrame, production_monthly: pd.DataFrame, request_eval: TrainingRequest
) -> None:
    # Flatten 2 of the 3 eligible wells' pre-cutoff series: a constant series has
    # a zero one-step naive MAE, so MASE is undefined for them. Only 1/3 eligible
    # wells keeps a defined MASE (< 50%), so gate 1 has too thin a base and the
    # evaluation must fail loudly rather than hand down a sliver-backed verdict.
    flat = production_monthly.copy()
    flat.loc[flat["well_id"].isin(["70002", "70004"]), "oil_prod_m3"] = 100.0
    test_rows = int((dataset["as_of_date"] == pd.Timestamp("2026-01-01")).sum())
    with pytest.raises(ValueError, match="representative portfolio verdict"):
        evaluate(StubModel(np.zeros(test_rows)), dataset, flat, request=request_eval)


def test_report_distributions_cover_contract_metrics(
    dataset: pd.DataFrame, production_monthly: pd.DataFrame, request_eval: TrainingRequest
) -> None:
    report = evaluate(
        StubModel(_test_targets(dataset)), dataset, production_monthly, request=request_eval
    )
    assert {"mase", "model_mae_m3", "naive_mae_m3"} <= set(report.distributions)
    for quantiles in report.distributions.values():
        assert set(quantiles) == {"p50", "p75", "p90"}


def test_returns_evaluation_report_type(
    dataset: pd.DataFrame, production_monthly: pd.DataFrame, request_eval: TrainingRequest
) -> None:
    report = evaluate(
        StubModel(_test_targets(dataset)), dataset, production_monthly, request=request_eval
    )
    assert isinstance(report, EvaluationReport)
