"""Champion model dependency for serving (F3-18).

Lazily loads the MLflow registry champion once per process and caches it, so the
first prediction pays the model-load cost and the rest reuse it. Exposed as a
FastAPI dependency (like ``get_connection``) so tests override it with a double
instead of standing up MLflow. Any registry/model failure surfaces as HTTP 503
— the endpoint stays up and degrades gracefully.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException
from petrocast_ml.config import MlSettings
from petrocast_ml.inference import ChampionModel, load_champion

from src.core.config import settings


@lru_cache(maxsize=1)
def _load_cached_champion() -> ChampionModel:
    """Load the champion once per process.

    ``lru_cache`` only memoizes successful returns, so a transient registry
    outage raises here and is retried on the next request rather than being
    cached as a permanent failure.
    """
    ml_settings = MlSettings(
        mlflow_tracking_uri=settings.mlflow_tracking_uri,
        mlflow_model_name=settings.mlflow_model_name,
        mlflow_model_alias=settings.mlflow_model_alias,
    )
    return load_champion(ml_settings)


def get_champion() -> ChampionModel:
    """FastAPI dependency: the cached champion, or HTTP 503 if unavailable."""
    try:
        return _load_cached_champion()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Model registry is unavailable. Try again later.",
        ) from exc


# Convenience type for annotated injection.
Champion = Annotated[ChampionModel, Depends(get_champion)]
