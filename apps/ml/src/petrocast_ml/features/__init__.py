"""Feature-store contract for ML consumers (contracts A and F).

``schema`` freezes the persisted projection and the model-input convention,
``dataset`` assembles training/inference frames from persisted rows, and
``engineering`` mirrors the dbt definitions for the point-in-time tests. The
``FeatureReader`` port stays the seam through which runtime consumers (F3-18)
plug their actual store access.
"""

from datetime import date
from typing import Protocol, runtime_checkable

import pandas as pd

from petrocast_ml.features.dataset import (
    as_model_input,
    build_inference_frame,
    build_training_dataset,
)
from petrocast_ml.features.engineering import compute_well_features
from petrocast_ml.features.schema import (
    AUDIT_COLUMNS,
    FEATURE_COLUMNS,
    FEATURE_TABLE_COLUMNS,
    HISTORY_FEATURES,
    HORIZON_COLUMN,
    KEY_COLUMNS,
    LAG_FEATURES,
    MAX_HORIZON,
    MODEL_INPUT_COLUMNS,
    NUMERIC_FEATURES,
    ROLLING_FEATURES,
    STATIC_FEATURES,
    TARGET_COLUMN,
    TARGET_MONTH_COLUMN,
    TREND_FEATURES,
    validate_feature_frame,
)


@runtime_checkable
class FeatureReader(Protocol):
    """Port implemented by consumers that read the persisted feature store."""

    def read(self, *, well_id: str, as_of_date: date) -> pd.DataFrame:
        """Return one persisted feature vector for a well and cutoff date."""
        ...


def read_features(
    reader: FeatureReader,
    *,
    well_id: str,
    as_of_date: date,
) -> pd.DataFrame:
    """Read features through the shared feature-store port."""
    return reader.read(well_id=well_id, as_of_date=as_of_date)


__all__ = [
    "AUDIT_COLUMNS",
    "FEATURE_COLUMNS",
    "FEATURE_TABLE_COLUMNS",
    "HISTORY_FEATURES",
    "HORIZON_COLUMN",
    "KEY_COLUMNS",
    "LAG_FEATURES",
    "MAX_HORIZON",
    "MODEL_INPUT_COLUMNS",
    "NUMERIC_FEATURES",
    "ROLLING_FEATURES",
    "STATIC_FEATURES",
    "TARGET_COLUMN",
    "TARGET_MONTH_COLUMN",
    "TREND_FEATURES",
    "FeatureReader",
    "as_model_input",
    "build_inference_frame",
    "build_training_dataset",
    "compute_well_features",
    "read_features",
    "validate_feature_frame",
]
