"""Prediction API contract — contrato D (ADR-0034, backlog F3-17).

Freezes the request/response shape consumed by F3-18 (inference runtime),
F3-20 (integrated endpoint), F3-21 (demo evidence) and F3-23 (CI smokes).
Grain and units follow ADR-0030: ``id_well`` is the ``well_id`` key of
``gold.fact_production`` (idpozo as text) and predictions are monthly oil
production in m³.
"""

from datetime import date

from pydantic import Field

from src.schemas.base import BaseSchema

HORIZON_MIN = 1
HORIZON_MAX = 12


class PredictionPoint(BaseSchema):
    month: date = Field(description="Primer día del mes predicho (YYYY-MM-01)")
    oil_prod_m3: float = Field(description="Producción de petróleo predicha para el mes, en m³")


class PredictionResponse(BaseSchema):
    id_well: str = Field(description="Identificador del pozo (well_id de gold.fact_production)")
    as_of_date: date = Field(description="Fecha de corte usada para generar la predicción")
    horizon: int = Field(
        ge=HORIZON_MIN,
        le=HORIZON_MAX,
        description="Horizonte solicitado, en meses",
    )
    model_version: str = Field(description="Versión del modelo que generó la predicción")
    predictions: list[PredictionPoint] = Field(
        description="Una predicción por mes, desde el mes siguiente a la fecha de corte",
    )


class PredictionError(BaseSchema):
    detail: str = Field(description="Descripción del error")


class PredictionValidationIssue(BaseSchema):
    loc: list[str | int] = Field(description="Ubicación del parámetro inválido")
    msg: str = Field(description="Descripción del error de validación")
    type: str = Field(description="Tipo del error de validación")


class PredictionValidationError(BaseSchema):
    detail: list[PredictionValidationIssue] = Field(
        description="Errores encontrados al validar los parámetros",
    )
