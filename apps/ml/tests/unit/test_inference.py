"""Unit tests for the champion inference runtime (F3-18)."""

from typing import Any

import numpy as np
import pandas as pd
import pytest

import petrocast_ml.inference as inference
from petrocast_ml.config import MlSettings
from petrocast_ml.features import FEATURE_SCHEMA, FeatureKind
from petrocast_ml.inference import load_champion, predict
from petrocast_ml.training.model import MODEL_FEATURE_COLUMNS


def _one_feature_row() -> pd.DataFrame:
    """A single persisted feature vector covering the model's input columns."""
    row: dict[str, Any] = {}
    for column, kind in FEATURE_SCHEMA.items():
        if kind is FeatureKind.NUMERIC:
            row[column] = 1.0
        elif kind is FeatureKind.TEXT:
            row[column] = "GOLFO_SAN_JORGE"
        else:  # DATE — not a model input, kept out of the frame
            continue
    return pd.DataFrame([row])


class _CapturingModel:
    """Echoes the horizon column so tests can assert the expansion and order."""

    def __init__(self) -> None:
        self.received: pd.DataFrame | None = None

    def predict(self, model_input: pd.DataFrame) -> Any:
        self.received = model_input
        return model_input["horizon"].to_numpy(dtype=float)


def test_predict_expands_one_row_into_ordered_horizons():
    model = _CapturingModel()

    result = predict(model, _one_feature_row(), horizon=3)

    # Returned in horizon order: index h-1 is the model's horizon = h.
    assert np.array_equal(result, np.array([1.0, 2.0, 3.0]))
    assert model.received is not None
    assert len(model.received) == 3
    # Column order is the frozen model signature (shared with training).
    assert list(model.received.columns) == list(MODEL_FEATURE_COLUMNS)


def test_predict_rejects_non_positive_horizon():
    with pytest.raises(ValueError, match="horizon must be >= 1"):
        predict(_CapturingModel(), _one_feature_row(), horizon=0)


def test_predict_rejects_multiple_feature_rows():
    two_rows = pd.concat([_one_feature_row(), _one_feature_row()], ignore_index=True)
    with pytest.raises(ValueError, match="exactly one feature row"):
        predict(_CapturingModel(), two_rows, horizon=2)


def test_load_champion_resolves_alias_to_concrete_version(monkeypatch):
    sentinel_model = object()

    class _Version:
        version = 9

    class _Client:
        def get_model_version_by_alias(self, name: str, alias: str) -> _Version:
            return _Version()

    monkeypatch.setattr(inference.mlflow, "set_tracking_uri", lambda uri: None)
    monkeypatch.setattr(inference.mlflow, "set_registry_uri", lambda uri: None)
    monkeypatch.setattr(inference.mlflow.lightgbm, "load_model", lambda uri: sentinel_model)
    monkeypatch.setattr(inference, "MlflowClient", lambda: _Client())

    settings = MlSettings(
        mlflow_tracking_uri="http://mlflow:5000",
        mlflow_model_name="petrocast-production",
        mlflow_model_alias="champion",
    )
    champion = load_champion(settings)

    assert champion.model is sentinel_model
    assert champion.version == "9"
    assert champion.uri == "models:/petrocast-production@champion"
