"""Prediction endpoint — contrato D (ADR-0034, backlog F3-17 / F3-18).

Serves the registry champion over persisted features: the loader resolves
``models:/<name>@<alias>`` (F3-16), the service reads the point-in-time feature
vector (contract A) and runs inference (F3-18). ``as_of_date`` is the request
cutoff; predictions cover the following ``horizon`` months. The HTTP contract
frozen by F3-17 is unchanged.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import verify_api_key
from src.core.db import DBConn
from src.core.serving import Champion
from src.schemas.prediction import (
    HORIZON_MAX,
    HORIZON_MIN,
    PredictionError,
    PredictionResponse,
    PredictionValidationError,
)
from src.services import prediction_service

router = APIRouter()


@router.get(
    "/predictions",
    response_model=PredictionResponse,
    response_model_by_alias=True,
    dependencies=[Depends(verify_api_key)],
    responses={
        403: {"description": "Missing or invalid API key", "model": PredictionError},
        404: {
            "description": "Well not found, or no persisted features at as_of_date",
            "model": PredictionError,
        },
        422: {
            "description": "Invalid query parameters",
            "model": PredictionValidationError,
        },
        503: {
            "description": "Model or feature store unavailable",
            "model": PredictionError,
        },
    },
)
def get_predictions(
    conn: DBConn,
    champion: Champion,
    id_well: str = Query(..., description="Identificador del pozo"),
    as_of_date: date = Query(..., description="Fecha de corte (YYYY-MM-DD)"),
    horizon: int = Query(
        ...,
        ge=HORIZON_MIN,
        le=HORIZON_MAX,
        description="Horizonte en meses (1-12)",
    ),
) -> PredictionResponse:
    try:
        return prediction_service.get_prediction(
            conn,
            champion,
            id_well=id_well,
            as_of_date=as_of_date,
            horizon=horizon,
        )
    except prediction_service.WellNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Well '{id_well}' not found") from exc
    except prediction_service.FeaturesNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Well '{id_well}' has no persisted features at {as_of_date.isoformat()}",
        ) from exc
