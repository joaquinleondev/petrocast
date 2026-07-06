"""Prediction API contract — contrato D (ADR-0034, backlog F3-17).

Freezes the request/response shape consumed by F3-18 (inference runtime),
F3-20 (integrated endpoint), F3-21 (demo evidence) and F3-23 (CI smokes).
Grain and units follow ADR-0030: ``id_well`` is the ``well_id`` key of
``gold.fact_production`` (idpozo as text) and predictions are monthly oil
production in m³.
"""

from datetime import date

from pydantic import ConfigDict, Field

from src.schemas.base import BaseSchema

HORIZON_MIN = 1
HORIZON_MAX = 12


class PredictionPoint(BaseSchema):
    month: date = Field(
        description="Primer día del mes predicho (YYYY-MM-01)",
        examples=["2024-04-01"],
    )
    oil_prod_m3: float = Field(
        description="Producción de petróleo predicha para el mes, en m³",
        examples=[1234.5],
    )


class PredictionResponse(BaseSchema):
    model_config = BaseSchema.model_config | ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id_well": "POZO-001",
                    "as_of_date": "2024-03-15",
                    "horizon": 3,
                    "model_version": "7",
                    "predictions": [
                        {"month": "2024-04-01", "oil_prod_m3": 1234.5},
                        {"month": "2024-05-01", "oil_prod_m3": 1180.2},
                        {"month": "2024-06-01", "oil_prod_m3": 1125.9},
                    ],
                }
            ]
        }
    )

    id_well: str = Field(
        description="Identificador del pozo (well_id de gold.fact_production)",
        examples=["POZO-001"],
    )
    as_of_date: date = Field(
        description="Fecha de corte usada para generar la predicción",
        examples=["2024-03-15"],
    )
    horizon: int = Field(
        ge=HORIZON_MIN,
        le=HORIZON_MAX,
        description="Horizonte solicitado, en meses",
        examples=[3],
    )
    model_version: str = Field(
        description="Versión del modelo que generó la predicción",
        examples=["7"],
    )
    predictions: list[PredictionPoint] = Field(
        description="Una predicción por mes, desde el mes siguiente a la fecha de corte",
    )


class PredictionError(BaseSchema):
    detail: str = Field(
        description="Descripción del error",
        examples=["Well 'POZO-001' not found"],
    )


class PredictionValidationIssue(BaseSchema):
    loc: list[str | int] = Field(
        description="Ubicación del parámetro inválido",
        examples=[["query", "horizon"]],
    )
    msg: str = Field(
        description="Descripción del error de validación",
        examples=["Input should be less than or equal to 12"],
    )
    type: str = Field(
        description="Tipo del error de validación",
        examples=["less_than_equal"],
    )


class PredictionValidationError(BaseSchema):
    detail: list[PredictionValidationIssue] = Field(
        description="Errores encontrados al validar los parámetros",
    )
