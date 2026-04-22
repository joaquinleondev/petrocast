from src.schemas.base import BaseSchema


class ForecastPoint(BaseSchema):
    date: str
    prod: float


class ForecastResponse(BaseSchema):
    id_well: str
    data: list[ForecastPoint]
