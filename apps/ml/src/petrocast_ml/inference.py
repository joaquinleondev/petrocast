"""Champion inference runtime (F3-18).

Loads the registry champion (contract B, ``models:/<name>@<alias>``) and turns a
single persisted feature vector (contract A) into a monthly production forecast
using the *exact* model signature training and evaluation feed LightGBM
(``prepare_model_input`` / ``MODEL_FEATURE_COLUMNS``). Direct multi-step: the
model takes ``horizon`` as an input column, so a horizon-``H`` request expands
the one feature row into ``H`` rows (``horizon = 1..H``) and predicts each.

Pure of any web/DB concern: the API layer (``apps/api``) reads the feature row
from the store and wires this into the endpoint (F3-18 wiring / F3-20).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import mlflow.lightgbm
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient
from numpy.typing import NDArray

from petrocast_ml.config import MlSettings, get_settings
from petrocast_ml.training.dataset import HORIZON_COLUMN
from petrocast_ml.training.model import prepare_model_input


@runtime_checkable
class PredictionModel(Protocol):
    """Minimal prediction contract shared by the LightGBM champion and doubles."""

    def predict(self, model_input: pd.DataFrame) -> object:
        """Predict values for an ordered feature frame."""
        ...


@dataclass(frozen=True, slots=True)
class ChampionModel:
    """A loaded champion plus the concrete registry version it resolved to.

    ``version`` is the numeric model version the ``@champion`` alias points at,
    surfaced so serving can audit *which* model answered each request.
    """

    model: PredictionModel
    version: str
    uri: str


def load_champion(settings: MlSettings | None = None) -> ChampionModel:
    """Load the MLflow model referenced by the configured champion alias.

    Resolves the alias to a concrete version for traceability. Propagates
    whatever MLflow raises when the tracking/registry server or the alias is
    unreachable (the API dependency maps that to HTTP 503).
    """
    settings = settings or get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_registry_uri(settings.mlflow_tracking_uri)

    uri = settings.champion_model_uri
    model = mlflow.lightgbm.load_model(uri)
    version = (
        MlflowClient()
        .get_model_version_by_alias(settings.mlflow_model_name, settings.mlflow_model_alias)
        .version
    )
    return ChampionModel(model=model, version=str(version), uri=uri)


def predict(
    model: PredictionModel,
    features: pd.DataFrame,
    *,
    horizon: int,
) -> NDArray[np.float64]:
    """Predict monthly production for horizons ``1..horizon`` from one feature row.

    ``features`` must be exactly one persisted feature vector (contract A). The
    returned array is ordered by horizon: index ``h - 1`` is the prediction for
    the model's ``horizon = h`` (target month ``as_of_date + (h - 1)``).
    """
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    if len(features) != 1:
        raise ValueError(f"inference expects exactly one feature row, got {len(features)}")

    steps = pd.concat(
        [features.assign(**{HORIZON_COLUMN: h}) for h in range(1, horizon + 1)],
        ignore_index=True,
    )
    model_input = prepare_model_input(steps)
    return np.asarray(model.predict(model_input), dtype=np.float64)


__all__ = ["ChampionModel", "PredictionModel", "load_champion", "predict"]
