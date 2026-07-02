from typing import Protocol, runtime_checkable

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from petrocast_ml.config import MlSettings


@runtime_checkable
class PredictionModel(Protocol):
    """Minimal prediction contract shared by MLflow pyfunc and test doubles."""

    def predict(self, model_input: pd.DataFrame) -> object:
        """Predict values for an ordered feature frame."""
        ...


def load_champion(settings: MlSettings | None = None) -> PredictionModel:
    """Load the MLflow model referenced by the configured champion alias."""
    del settings
    raise NotImplementedError("Champion loading is implemented by F3-18")


def predict(
    model: PredictionModel,
    features: pd.DataFrame,
    *,
    horizon: int,
) -> NDArray[np.float64]:
    """Generate monthly production predictions for the requested horizon."""
    del model, features, horizon
    raise NotImplementedError("Inference is implemented by F3-18")


__all__ = ["PredictionModel", "load_champion", "predict"]
