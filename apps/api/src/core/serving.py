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


def champion_health() -> dict[str, str]:
    """Serving state of the champion for health reporting.

    Never triggers a model load: the champion loads lazily on the first
    prediction, so ``not_loaded`` on a fresh process is normal, not a failure.
    """
    if _load_cached_champion.cache_info().currsize == 0:
        configured_uri = f"models:/{settings.mlflow_model_name}@{settings.mlflow_model_alias}"
        return {"status": "not_loaded", "model_uri": configured_uri}
    champion = _load_cached_champion()
    return {
        "status": "loaded",
        "model_uri": champion.uri,
        "model_version": champion.version,
    }


# Convenience type for annotated injection.
Champion = Annotated[ChampionModel, Depends(get_champion)]
