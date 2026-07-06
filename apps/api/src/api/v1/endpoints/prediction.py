"""Prediction endpoint — contrato D (ADR-0034, backlog F3-17 / F3-18).

Serves the registry champion over persisted features: the loader resolves
``models:/<name>@<alias>`` (F3-16), the service reads the point-in-time feature
vector (contract A) and runs inference (F3-18). ``as_of_date`` is the request
cutoff; predictions cover the following ``horizon`` months. The HTTP contract
frozen by F3-17 is unchanged.
"""

import re
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BeforeValidator

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

_ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Feature store timestamps are pandas ``Timestamp`` (int64 ns since epoch),
# representable roughly in [1677-09-22, 2262-04-11]. Bound ``as_of_date`` to a
# realistic well-production window well inside that range so out-of-range
# dates fail cleanly with 422 instead of overflowing to NaT deep in feature
# validation (contract A).
_AS_OF_DATE_MIN = date(1900, 1, 1)
_AS_OF_DATE_MAX = date(2100, 12, 31)


def _reject_non_iso_date(value: object) -> object:
    """Reject non-ISO-8601 strings before pydantic's lax ``date`` coercion.

    Pydantic v2 parses bare numeric strings (e.g. ``"0"``) as Unix
    timestamps in lax mode, which would otherwise let a malformed
    ``as_of_date`` query value silently through as a valid (if surprising)
    date instead of failing with 422. Query params always arrive as raw
    strings, so this only tightens the one accepted shape; the declared
    OpenAPI type/format (``string`` / ``format: date``) is unaffected.
    """
    if isinstance(value, str) and not _ISO_DATE_PATTERN.fullmatch(value):
        raise ValueError("Input should be a valid date in YYYY-MM-DD format")
    return value


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
    *,
    id_well: str = Query(
        ...,
        description="Identificador del pozo",
        openapi_examples={
            "pozo-001": {
                "summary": "Pozo POZO-001",
                "value": "POZO-001",
            },
        },
    ),
    as_of_date: Annotated[
        date,
        BeforeValidator(_reject_non_iso_date),
        Query(
            ge=_AS_OF_DATE_MIN,
            le=_AS_OF_DATE_MAX,
            description="Fecha de corte (YYYY-MM-DD)",
            openapi_examples={
                "marzo-2024": {
                    "summary": "Corte a 2024-03-15",
                    "value": "2024-03-15",
                },
            },
        ),
    ],
    horizon: int = Query(
        ...,
        ge=HORIZON_MIN,
        le=HORIZON_MAX,
        description="Horizonte en meses (1-12)",
        openapi_examples={
            "tres-meses": {
                "summary": "Horizonte de 3 meses",
                "value": 3,
            },
        },
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
