"""Public contracts for Petrocast machine-learning workflows."""

from petrocast_ml.config import MlSettings, get_settings
from petrocast_ml.features import (
    CONTRACT_COLUMNS,
    CONTRACT_SCHEMA,
    FEATURE_COLUMNS,
    FEATURE_SCHEMA,
    KEY_COLUMNS,
    KEY_SCHEMA,
    FeatureKind,
    FeatureReader,
    read_features,
    validate_feature_frame,
)
from petrocast_ml.inference import PredictionModel, load_champion, predict
from petrocast_ml.registry import (
    CandidateMetadataError,
    CandidateNotApprovedError,
    MlflowModelRegistry,
    ModelRegistry,
    ModelVersion,
    RegistryError,
    create_registry_client,
    promote_champion,
    register_candidate,
)
from petrocast_ml.tracking import (
    RunMetadata,
    TrackingClient,
    create_tracking_client,
    record_training_run,
)
from petrocast_ml.training import TrainableModel, TrainingRequest, TrainingResult, train

__all__ = [
    "CONTRACT_COLUMNS",
    "CONTRACT_SCHEMA",
    "FEATURE_COLUMNS",
    "FEATURE_SCHEMA",
    "KEY_COLUMNS",
    "KEY_SCHEMA",
    "CandidateMetadataError",
    "CandidateNotApprovedError",
    "FeatureKind",
    "FeatureReader",
    "MlSettings",
    "MlflowModelRegistry",
    "ModelRegistry",
    "ModelVersion",
    "PredictionModel",
    "RegistryError",
    "RunMetadata",
    "TrackingClient",
    "TrainableModel",
    "TrainingRequest",
    "TrainingResult",
    "create_registry_client",
    "create_tracking_client",
    "get_settings",
    "load_champion",
    "predict",
    "promote_champion",
    "read_features",
    "record_training_run",
    "register_candidate",
    "train",
    "validate_feature_frame",
]
