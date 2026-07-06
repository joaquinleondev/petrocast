"""Prediction service — champion inference over persisted features (F3-18).

Orchestrates the read-model runtime behind ``GET /api/v1/predictions``: resolve
the well, read its persisted feature vector, run the champion, and shape the
frozen response (contract D).

``as_of_date`` is the request cutoff (last observed month). The model's cutoff
is the *first unknown month* — the month after — so the feature row is read at
``as_of_date + 1`` and horizon step ``s`` predicts month ``as_of_date + s``,
which keeps the F3-17 HTTP contract ("desde el mes siguiente") intact.
"""

import logging
from datetime import date
from typing import Any

import psycopg
from petrocast_ml.features import validate_feature_frame
from petrocast_ml.inference import ChampionModel, predict

from src.repositories import feature_repository, well_repository
from src.schemas.prediction import PredictionPoint, PredictionResponse

logger = logging.getLogger(__name__)


class PredictionError(Exception):
    """Base class for prediction failures the endpoint maps to an HTTP status."""


class WellNotFoundError(PredictionError):
    """The requested well is absent from ``gold.dim_well``."""


class FeaturesNotFoundError(PredictionError):
    """No persisted feature vector for the well at the model cutoff."""


def _month_start(base: date, offset: int) -> date:
    """First day of the month *offset* months after *base* (day-of-month ignored)."""
    total = base.year * 12 + (base.month - 1) + offset
    return date(total // 12, total % 12 + 1, 1)


def get_prediction(
    conn: psycopg.Connection[Any],
    champion: ChampionModel,
    *,
    id_well: str,
    as_of_date: date,
    horizon: int,
) -> PredictionResponse:
    """Predict *horizon* months for *id_well* from persisted features.

    Raises:
        WellNotFoundError: the well is unknown.
        FeaturesNotFoundError: the model cutoff has no persisted feature vector.
    """
    if not well_repository.exists(conn, id_well):
        raise WellNotFoundError(id_well)

    feature_cutoff = _month_start(as_of_date, 1)
    features = feature_repository.read(conn, well_id=id_well, as_of_date=feature_cutoff)
    if features.empty:
        raise FeaturesNotFoundError(id_well)
    features = validate_feature_frame(features)

    values = predict(champion.model, features, horizon=horizon)
    predictions = [
        PredictionPoint(month=_month_start(as_of_date, step), oil_prod_m3=float(value))
        for step, value in enumerate(values, start=1)
    ]

    logger.info(
        "served prediction id_well=%s as_of_date=%s horizon=%s model_version=%s",
        id_well,
        as_of_date.isoformat(),
        horizon,
        champion.version,
    )
    return PredictionResponse(
        id_well=id_well,
        as_of_date=as_of_date,
        horizon=horizon,
        model_version=champion.version,
        predictions=predictions,
    )
