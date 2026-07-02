"""Model artifact persistence with dataset and code metadata (F3-13).

A training run leaves two files in the output directory: ``model.txt`` (the
LightGBM booster, loadable without sklearn) and ``metadata.json`` describing
what was trained on and with which code — the reproducibility link ADR-0032
formalizes once MLflow tracking lands (F3-14). Until then the artifact is
self-describing.
"""

import json
import os
from datetime import UTC, datetime
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

import lightgbm
import pandas as pd

from petrocast_ml.training.contracts import TrainingRequest, TrainingResult
from petrocast_ml.training.dataset import HORIZON_COLUMN
from petrocast_ml.training.model import CATEGORICAL_FEATURES, MODEL_FEATURE_COLUMNS

MODEL_FILE = "model.txt"
METADATA_FILE = "metadata.json"


def _package_version() -> str:
    try:
        return importlib_metadata.version("petrocast-ml")
    except importlib_metadata.PackageNotFoundError:
        return "unknown"


def save_training_artifact(
    result: TrainingResult,
    *,
    request: TrainingRequest,
    dataset: pd.DataFrame,
    output_dir: Path,
) -> Path:
    """Persist booster + metadata; returns the artifact directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    booster = result.model.booster_  # type: ignore[attr-defined]
    booster.save_model(str(output_dir / MODEL_FILE))

    metadata: dict[str, Any] = {
        "request": {
            "as_of_date": request.as_of_date.isoformat(),
            "features_version": request.features_version,
            "horizon": request.horizon,
            "validation_cutoffs": request.validation_cutoffs,
        },
        "dataset": {
            "rows": len(dataset),
            "wells": int(dataset["well_id"].nunique()),
            "cutoffs": sorted(
                pd.Timestamp(cutoff).date().isoformat() for cutoff in dataset["as_of_date"].unique()
            ),
            "horizons": sorted(int(h) for h in dataset[HORIZON_COLUMN].unique()),
        },
        "model": {
            "params": result.model.get_params(),  # type: ignore[attr-defined]
            "feature_columns": list(MODEL_FEATURE_COLUMNS),
            "categorical_features": list(CATEGORICAL_FEATURES),
        },
        "metrics": dict(result.metrics),
        "code": {
            "petrocast_ml_version": _package_version(),
            "lightgbm_version": lightgbm.__version__,
            "git_sha": os.environ.get("PETROCAST_GIT_SHA"),
        },
        "trained_at": datetime.now(tz=UTC).isoformat(),
    }
    (output_dir / METADATA_FILE).write_text(json.dumps(metadata, indent=2, default=str))
    return output_dir


def load_booster(artifact_dir: Path) -> lightgbm.Booster:
    """Load the persisted booster (the inference runtime of F3-18 reuses this)."""
    return lightgbm.Booster(model_file=str(artifact_dir / MODEL_FILE))


__all__ = ["METADATA_FILE", "MODEL_FILE", "load_booster", "save_training_artifact"]
