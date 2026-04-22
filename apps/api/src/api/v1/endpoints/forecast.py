from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import verify_api_key
from src.schemas.forecast import ForecastResponse
from src.services import forecast_service

router = APIRouter()


@router.get(
    "/forecast",
    response_model=ForecastResponse,
    response_model_by_alias=True,
    dependencies=[Depends(verify_api_key)],
    responses={
        400: {"description": "Invalid date range"},
        403: {"description": "Missing or invalid API key"},
        404: {"description": "Well not found"},
    },
)
def get_forecast(
    id_well: str = Query(..., description="Identificador del pozo"),
    date_start: date = Query(..., description="Fecha de inicio (YYYY-MM-DD)"),
    date_end: date = Query(..., description="Fecha de fin (YYYY-MM-DD)"),
) -> ForecastResponse:
    if date_start > date_end:
        raise HTTPException(
            status_code=400, detail="date_start must be before date_end"
        )

    result = forecast_service.get_forecast(id_well, date_start, date_end)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Well '{id_well}' not found")

    return result
