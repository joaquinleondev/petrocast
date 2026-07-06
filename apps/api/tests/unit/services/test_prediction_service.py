"""Unit tests for the prediction service (F3-18).

Exercise the orchestration against the fake connection + champion double from
conftest: a successful prediction and the two domain error paths.
"""

from datetime import date

import pytest

from src.services import prediction_service
from src.services.prediction_service import (
    FeaturesNotFoundError,
    WellNotFoundError,
    get_prediction,
)
from tests.conftest import FAKE_MODEL_VERSION

AS_OF = date(2024, 3, 15)


def test_successful_prediction_maps_horizon_to_following_months(fake_conn, fake_champion):
    response = get_prediction(
        fake_conn, fake_champion, id_well="POZO-001", as_of_date=AS_OF, horizon=3
    )

    assert response.id_well == "POZO-001"
    assert response.as_of_date == AS_OF
    assert response.horizon == 3
    assert response.model_version == FAKE_MODEL_VERSION
    months = [point.month for point in response.predictions]
    values = [point.oil_prod_m3 for point in response.predictions]
    assert months == [date(2024, 4, 1), date(2024, 5, 1), date(2024, 6, 1)]
    assert values == [100.0, 200.0, 300.0]


def test_reads_features_at_the_month_after_the_cutoff(fake_conn, fake_champion, monkeypatch):
    captured: dict[str, object] = {}
    real_read = prediction_service.feature_repository.read

    def spy_read(conn, *, well_id, as_of_date):
        captured["as_of_date"] = as_of_date
        return real_read(conn, well_id=well_id, as_of_date=as_of_date)

    monkeypatch.setattr(prediction_service.feature_repository, "read", spy_read)

    get_prediction(fake_conn, fake_champion, id_well="POZO-001", as_of_date=AS_OF, horizon=1)

    # Model cutoff = first unknown month = the month after the request cutoff.
    assert captured["as_of_date"] == date(2024, 4, 1)


def test_unknown_well_raises_well_not_found(fake_conn, fake_champion):
    with pytest.raises(WellNotFoundError):
        get_prediction(fake_conn, fake_champion, id_well="NOPE-999", as_of_date=AS_OF, horizon=3)


def test_well_without_features_raises_features_not_found(fake_conn, fake_champion):
    # POZO-003 exists in dim_well but has no persisted feature row.
    with pytest.raises(FeaturesNotFoundError):
        get_prediction(fake_conn, fake_champion, id_well="POZO-003", as_of_date=AS_OF, horizon=3)
