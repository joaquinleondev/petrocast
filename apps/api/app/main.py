from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query

from app.auth import verify_api_key
from app.mock_data import WELLS, generate_forecast
from app.schemas import ForecastResponse, WellInfo

app = FastAPI(
    title="Oil & Gas Forecast API",
    version="1.0.0",
    description="API para consultar el listado de pozos y sus pronósticos de producción.",
)


@app.get(
    "/api/v1/wells",
    response_model=list[WellInfo],
    dependencies=[Depends(verify_api_key)],
)
def get_wells(
    date_query: date = Query(..., description="Fecha para la consulta (YYYY-MM-DD)"),
):
    return WELLS


@app.get(
    "/api/v1/forecast",
    response_model=ForecastResponse,
    dependencies=[Depends(verify_api_key)],
)
def get_forecast(
    id_well: str = Query(..., description="Identificador del pozo"),
    date_start: date = Query(..., description="Fecha de inicio (YYYY-MM-DD)"),
    date_end: date = Query(..., description="Fecha de fin (YYYY-MM-DD)"),
):
    if date_start > date_end:
        raise HTTPException(status_code=400, detail="date_start must be before date_end")

    data = generate_forecast(id_well, date_start, date_end)
    if not data:
        raise HTTPException(status_code=404, detail=f"Well '{id_well}' not found")

    return ForecastResponse(id_well=id_well, data=data)
