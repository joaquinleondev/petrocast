"""Baseline training pipeline (F3-13) behind the contracts frozen in F3-07."""

from petrocast_ml.training.artifact import (
    METADATA_FILE,
    MODEL_FILE,
    load_booster,
    save_training_artifact,
)
from petrocast_ml.training.contracts import TrainableModel, TrainingRequest, TrainingResult
from petrocast_ml.training.dataset import (
    HORIZON_COLUMN,
    NAIVE_COLUMN,
    TARGET_COLUMN,
    TemporalSplit,
    build_training_dataset,
    temporal_split,
)
from petrocast_ml.training.model import (
    CATEGORICAL_FEATURES,
    FIXED_PARAMS,
    MODEL_FEATURE_COLUMNS,
    create_model,
    prepare_model_input,
)
from petrocast_ml.training.pipeline import train

__all__ = [
    "CATEGORICAL_FEATURES",
    "FIXED_PARAMS",
    "HORIZON_COLUMN",
    "METADATA_FILE",
    "MODEL_FEATURE_COLUMNS",
    "MODEL_FILE",
    "NAIVE_COLUMN",
    "TARGET_COLUMN",
    "TemporalSplit",
    "TrainableModel",
    "TrainingRequest",
    "TrainingResult",
    "build_training_dataset",
    "create_model",
    "load_booster",
    "prepare_model_input",
    "save_training_artifact",
    "temporal_split",
    "train",
]
