"""Prediction endpoint — exposes contrato D (ADR-0034, backlog F3-17).

Placeholder implementation until the ML runtime lands: predictions are a
naive persistence of the last observed month at or before ``as_of_date``
(``model_version = "naive-persistence-mock"``). F3-18 replaces the internals
with the champion model + feature store and F3-20 wires the integration;
the HTTP contract defined here must not change.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import verify_api_key
from src.core.db import DBConn
from src.repositories import forecast_repository, well_repository
from src.schemas.prediction import (
    HORIZON_MAX,
    HORIZON_MIN,
    PredictionError,
    PredictionPoint,
    PredictionResponse,
)

router = APIRouter()

MOCK_MODEL_VERSION = "naive-persistence-mock"


def _add_months(base: date, months: int) -> date:
    """Return the first day of the month *months* after *base*."""
    total = base.year * 12 + (base.month - 1) + months
    return date(total // 12, total % 12 + 1, 1)


@router.get(
    "/predictions",
    response_model=PredictionResponse,
    response_model_by_alias=True,
    dependencies=[Depends(verify_api_key)],
    responses={
        403: {"description": "Missing or invalid API key", "model": PredictionError},
        404: {
            "description": "Well not found, or no production history at as_of_date",
            "model": PredictionError,
        },
        503: {
            "description": "Model or feature store unavailable",
            "model": PredictionError,
        },
    },
)
def get_predictions(
    conn: DBConn,
    id_well: str = Query(..., description="Identificador del pozo"),
    as_of_date: date = Query(..., description="Fecha de corte (YYYY-MM-DD)"),
    horizon: int = Query(
        ...,
        ge=HORIZON_MIN,
        le=HORIZON_MAX,
        description="Horizonte en meses (1-12)",
    ),
) -> PredictionResponse:
    if not well_repository.exists(conn, id_well):
        raise HTTPException(status_code=404, detail=f"Well '{id_well}' not found")

    history = forecast_repository.generate(conn, id_well, date.min, as_of_date)
    if not history:
        raise HTTPException(
            status_code=404,
            detail=f"Well '{id_well}' has no production history at {as_of_date.isoformat()}",
        )

    last = history[-1]
    last_month = date.fromisoformat(str(last["date"]))
    last_value = float(last["prod"])

    return PredictionResponse(
        id_well=id_well,
        as_of_date=as_of_date,
        horizon=horizon,
        model_version=MOCK_MODEL_VERSION,
        predictions=[
            PredictionPoint(month=_add_months(last_month, step), oil_prod_m3=last_value)
            for step in range(1, horizon + 1)
        ],
    )
