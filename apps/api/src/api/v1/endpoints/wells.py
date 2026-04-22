from datetime import date

from fastapi import APIRouter, Depends, Query

from src.api.deps import verify_api_key
from src.schemas.well import WellInfo
from src.services import well_service

router = APIRouter()


@router.get(
    "/wells",
    response_model=list[WellInfo],
    response_model_by_alias=True,
    dependencies=[Depends(verify_api_key)],
    responses={403: {"description": "Missing or invalid API key"}},
)
def get_wells(
    date_query: date = Query(..., description="Fecha para la consulta (YYYY-MM-DD)"),
) -> list[WellInfo]:
    del date_query
    return well_service.get_all_wells()
