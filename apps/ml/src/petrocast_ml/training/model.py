"""Baseline model definition (F3-13): one global LightGBM for every well.

ADR-0030 fixes the modeling decision: a single LGBMRegressor trained over all
wells with the contract-A features plus ``horizon`` as an input (direct
multi-step strategy) and the dim_well statics as native categoricals, which is
what gives cold-start wells a reasonable prediction. Parameters are FIXED —
the baseline must be reproducible and evaluable before any tuning; deliberate
overrides (e.g. tiny smoke configs in tests) go through ``params``.
"""

from typing import Any, Final

import pandas as pd
from lightgbm import LGBMRegressor

from petrocast_ml.features import FEATURE_SCHEMA, FeatureKind
from petrocast_ml.training.dataset import HORIZON_COLUMN

#: dim_well statics, handled by LightGBM as native categorical splits.
CATEGORICAL_FEATURES: Final[tuple[str, ...]] = tuple(
    name for name, kind in FEATURE_SCHEMA.items() if kind is FeatureKind.TEXT
)

#: Model input signature: contract-A numerics, statics, then the horizon.
MODEL_FEATURE_COLUMNS: Final[tuple[str, ...]] = (
    tuple(name for name, kind in FEATURE_SCHEMA.items() if kind is FeatureKind.NUMERIC)
    + CATEGORICAL_FEATURES
    + (HORIZON_COLUMN,)
)

#: Fixed baseline parameters (F3-13): deterministic, no tuning.
FIXED_PARAMS: Final[dict[str, Any]] = {
    "objective": "regression",
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 20,
    "random_state": 42,
    "deterministic": True,
    "force_row_wise": True,
    "verbosity": -1,
}


def prepare_model_input(frame: pd.DataFrame) -> pd.DataFrame:
    """Project a dataset onto the model signature, casting statics to category.

    Column order is part of the signature: every consumer (training F3-13,
    inference F3-18) must feed LightGBM the exact same layout.
    """
    missing = [column for column in MODEL_FEATURE_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"dataset is missing model feature columns: {missing}")
    model_input = frame.loc[:, list(MODEL_FEATURE_COLUMNS)].copy()
    for column in CATEGORICAL_FEATURES:
        model_input[column] = model_input[column].astype("category")
    return model_input


def create_model(params: dict[str, Any] | None = None) -> LGBMRegressor:
    """Instantiate the baseline estimator with the fixed (or overridden) params."""
    return LGBMRegressor(**{**FIXED_PARAMS, **(params or {})})


__all__ = [
    "CATEGORICAL_FEATURES",
    "FIXED_PARAMS",
    "MODEL_FEATURE_COLUMNS",
    "create_model",
    "prepare_model_input",
]
