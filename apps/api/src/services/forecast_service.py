from datetime import date
from typing import Any

import psycopg

from src.repositories import forecast_repository
from src.schemas.forecast import ForecastPoint, ForecastResponse


def get_forecast(
    conn: psycopg.Connection[Any],
    id_well: str,
    date_start: date,
    date_end: date,
) -> ForecastResponse | None:
    raw = forecast_repository.generate(conn, id_well, date_start, date_end)
    if not raw:
        return None
    return ForecastResponse(
        id_well=id_well,
        data=[ForecastPoint(date=str(point["date"]), prod=float(point["prod"])) for point in raw],
    )
