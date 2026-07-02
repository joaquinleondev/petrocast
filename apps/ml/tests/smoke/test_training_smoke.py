"""End-to-end training smoke on committed fixtures (F3-13): no DB, no MLflow.

Documents the baseline assumptions: single global LightGBM over all wells,
horizon as an input feature (direct multi-step, ADR-0030), temporal split with
the request cutoff as single-origin test, and the persistence naive computed
on exactly the same split.
"""

import json
import math
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from petrocast_ml.training import (
    CATEGORICAL_FEATURES,
    METADATA_FILE,
    MODEL_FEATURE_COLUMNS,
    MODEL_FILE,
    NAIVE_COLUMN,
    TARGET_COLUMN,
    TrainingRequest,
    build_training_dataset,
    load_booster,
    prepare_model_input,
    save_training_artifact,
    train,
)

#: Tiny deliberate overrides so the smoke trains on ~a dozen rows in <1s; the
#: production defaults stay in FIXED_PARAMS.
SMOKE_PARAMS = {"n_estimators": 10, "min_child_samples": 1, "num_leaves": 4}


@pytest.fixture
def dataset(production_monthly: pd.DataFrame, well_features: pd.DataFrame) -> pd.DataFrame:
    return build_training_dataset(well_features, production_monthly, horizons=(1, 2, 3))


@pytest.fixture
def request_smoke() -> TrainingRequest:
    return TrainingRequest(as_of_date=date(2026, 1, 1), features_version="fixtures", horizon=3)


def test_training_smoke_end_to_end(
    dataset: pd.DataFrame,
    request_smoke: TrainingRequest,
    expected_naive_backtest: pd.DataFrame,
    tmp_path: Path,
) -> None:
    result = train(dataset, dataset[TARGET_COLUMN], request=request_smoke, params=SMOKE_PARAMS)

    assert result.training_rows == int(result.metrics["train_rows"]) > 0
    for key in ("model_mae_m3", "model_rmse_m3", "naive_mae_m3", "naive_rmse_m3"):
        assert math.isfinite(result.metrics[key]), key

    # The naive baseline on the test split equals the frozen backtest fixture.
    expected_naive_mae = (
        (expected_naive_backtest["actual_m3"] - expected_naive_backtest["naive_forecast_m3"])
        .abs()
        .mean()
    )
    assert result.metrics["naive_mae_m3"] == pytest.approx(expected_naive_mae)
    assert result.metrics["test_rows"] == float(len(expected_naive_backtest))

    artifact_dir = save_training_artifact(
        result, request=request_smoke, dataset=dataset, output_dir=tmp_path / "artifact"
    )
    assert (artifact_dir / MODEL_FILE).exists()
    metadata = json.loads((artifact_dir / METADATA_FILE).read_text())
    assert metadata["request"]["as_of_date"] == "2026-01-01"
    assert metadata["dataset"]["rows"] == len(dataset)
    assert metadata["model"]["feature_columns"] == list(MODEL_FEATURE_COLUMNS)
    assert metadata["metrics"]["naive_mae_m3"] == pytest.approx(expected_naive_mae)
    assert metadata["code"]["lightgbm_version"]

    # The persisted booster is loadable standalone and predicts on the signature.
    booster = load_booster(artifact_dir)
    test_rows = dataset.loc[dataset["as_of_date"] == pd.Timestamp(request_smoke.as_of_date)]
    reloaded = booster.predict(prepare_model_input(test_rows))
    assert len(reloaded) == len(test_rows)
    assert all(math.isfinite(value) for value in reloaded)


def test_training_is_deterministic(dataset: pd.DataFrame, request_smoke: TrainingRequest) -> None:
    """Fixed params + fixed seed: two runs produce identical test metrics."""
    first = train(dataset, dataset[TARGET_COLUMN], request=request_smoke, params=SMOKE_PARAMS)
    second = train(dataset, dataset[TARGET_COLUMN], request=request_smoke, params=SMOKE_PARAMS)
    assert dict(first.metrics) == dict(second.metrics)


def test_model_input_signature(dataset: pd.DataFrame) -> None:
    """Column order and categorical dtypes are part of the model signature."""
    model_input = prepare_model_input(dataset)
    assert list(model_input.columns) == list(MODEL_FEATURE_COLUMNS)
    for column in CATEGORICAL_FEATURES:
        assert isinstance(model_input[column].dtype, pd.CategoricalDtype)
    assert NAIVE_COLUMN not in model_input.columns, "the baseline must never leak into the model"
