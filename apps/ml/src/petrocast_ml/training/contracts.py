"""Training contracts shared across the ML pipeline (frozen in F3-07).

``TrainingRequest.as_of_date`` doubles as the single-origin evaluation cutoff
of contract F (ADR-0030): rows with that knowledge cutoff form the test split,
older cutoffs feed train/validation. ``validation_cutoffs`` reserves the N
cutoffs immediately before the test one for validation (0 keeps everything in
train, enough for the fixed-parameter baseline of F3-13).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Protocol, Self, runtime_checkable

import numpy as np
import pandas as pd
from numpy.typing import NDArray


@runtime_checkable
class TrainableModel(Protocol):
    """Estimator contract required by the baseline training pipeline."""

    def fit(self, features: pd.DataFrame, target: pd.Series) -> Self:
        """Fit the estimator and return it."""
        ...

    def predict(self, features: pd.DataFrame) -> NDArray[np.float64]:
        """Predict target values."""
        ...


@dataclass(frozen=True, slots=True)
class TrainingRequest:
    as_of_date: date
    features_version: str
    horizon: int = 12
    validation_cutoffs: int = 0


@dataclass(frozen=True, slots=True)
class TrainingResult:
    model: TrainableModel
    metrics: Mapping[str, float]
    training_rows: int


__all__ = ["TrainableModel", "TrainingRequest", "TrainingResult"]
