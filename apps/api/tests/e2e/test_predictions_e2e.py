"""Real end-to-end champion serving for GET /api/v1/predictions (F3-20).

Every other test in this suite fakes the champion with a double
(``get_champion`` override -> ``_FakeChampionModel`` in ``conftest.py``), so
none of them ever exercise ``serving.load_champion`` ->
``mlflow.lightgbm.load_model`` -> ``@champion`` alias resolution against a
real MLflow registry. This test closes that gap: it trains a tiny real
LightGBM on the offline ML fixtures (``apps/ml/tests/fixtures``), logs +
registers + promotes it to ``@champion`` on a throwaway SQLite-backed MLflow
(no network, no Postgres), points the app's ``get_champion`` dependency at the
resulting ``ChampionModel``, and asserts the endpoint answers with a real
prediction traced to the real registered model version.

The feature store stays the fake from ``conftest.py`` -- a real Postgres
feature store is already covered by the ``data-pipeline`` CI job. Only the
model side of the serving chain is real here.
"""

from __future__ import annotations

import math
from collections.abc import Generator
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("lightgbm")
pytest.importorskip("mlflow")

import mlflow
from fastapi.testclient import TestClient
from mlflow.tracking import MlflowClient
from petrocast_ml.config import ML_APP_DIR, MlSettings
from petrocast_ml.inference import ChampionModel, load_champion
from petrocast_ml.registry import (
    create_registry_client,
    promote_champion,
    register_candidate,
)
from petrocast_ml.tracking import (
    GATES_PASSED_TAG,
    RunMetadata,
    create_tracking_client,
    record_training_run,
)
from petrocast_ml.training import (
    TARGET_COLUMN,
    TrainingRequest,
    build_training_dataset,
    save_training_artifact,
    train,
)

from src.core.serving import get_champion
from src.main import app
from tests.conftest import FAKE_MODEL_VERSION

pytestmark = pytest.mark.e2e

# Offline contract-A fixtures apps/ml already maintains for its own training
# smokes (F3-14/F3-16) -- reused here instead of duplicating fixture data.
_FIXTURES_DIR = ML_APP_DIR / "tests" / "fixtures"

_MODEL_NAME = "petrocast-production-e2e"
_EXPERIMENT_NAME = "f3-20-predictions-e2e"
_TRAIN_AS_OF_DATE = date(2026, 1, 1)

# Tiny/deterministic: this only needs to prove the serving chain loads and
# runs a *real* LightGBM end to end, not to produce an accurate forecast.
_TINY_PARAMS = {
    "n_estimators": 10,
    "min_child_samples": 1,
    "num_leaves": 4,
    "deterministic": True,
    "force_row_wise": True,
}


def _load_ml_fixtures() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load apps/ml's offline contract-A fixtures (well_features + production)."""
    well_features = pd.read_csv(
        _FIXTURES_DIR / "well_features.csv",
        dtype={"well_id": str},
        parse_dates=["as_of_date", "last_observed_month"],
    )
    production_monthly = pd.read_csv(
        _FIXTURES_DIR / "production_monthly.csv",
        dtype={"well_id": str},
        parse_dates=["production_month"],
    )
    return well_features, production_monthly


def _train_register_and_promote_champion(tracking_uri: str, artifact_root: Path) -> MlSettings:
    """Train a real tiny LightGBM and promote it to ``@champion`` on ``tracking_uri``.

    Mirrors the two patterns apps/ml already validates separately: the
    train+log round-trip (``tests/smoke/test_tracking_mlflow.py``) and the
    register+promote round-trip (``tests/smoke/test_registry_mlflow.py``) --
    chained here so the resulting alias points at a genuinely loadable model.
    """
    settings = MlSettings(
        mlflow_tracking_uri=tracking_uri,
        mlflow_artifact_root=artifact_root.as_uri(),
        mlflow_experiment_name=_EXPERIMENT_NAME,
        mlflow_model_name=_MODEL_NAME,
        mlflow_model_alias="champion",
    )
    # Pre-create the experiment with an explicit artifact_location: otherwise
    # mlflow.set_experiment (called by MlflowTrackingClient) creates it lazily
    # with mlflow's default artifact root, which lands outside tmp_path.
    MlflowClient(tracking_uri=tracking_uri).create_experiment(
        settings.mlflow_experiment_name, artifact_location=artifact_root.as_uri()
    )

    well_features, production_monthly = _load_ml_fixtures()
    dataset = build_training_dataset(well_features, production_monthly, horizons=(1, 2, 3))
    request = TrainingRequest(
        as_of_date=_TRAIN_AS_OF_DATE, features_version="fixtures-e2e", horizon=3
    )
    result = train(dataset, dataset[TARGET_COLUMN], request=request, params=_TINY_PARAMS)

    artifact_dir = save_training_artifact(
        result, request=request, dataset=dataset, output_dir=artifact_root.parent / "artifact"
    )
    run_metadata = RunMetadata(
        as_of_date=_TRAIN_AS_OF_DATE, features_version="fixtures-e2e", git_commit="f3-20-e2e"
    )
    tracking_client = create_tracking_client(settings)
    run_id = record_training_run(
        tracking_client,
        request=request,
        result=result,
        dataset=dataset,
        run_metadata=run_metadata,
        artifact_dir=artifact_dir,
    )
    # record_training_run only tags gates_passed when an EvaluationReport is
    # supplied (F3-15); this test skips the full evaluation pipeline, so tag
    # the run directly -- promote_champion refuses to move the alias without it.
    MlflowClient(tracking_uri=tracking_uri).set_tag(run_id, GATES_PASSED_TAG, "true")

    registry = create_registry_client(settings)
    candidate = register_candidate(registry, run_id=run_id, settings=settings)
    promote_champion(registry, version=candidate.version, settings=settings)
    return settings


@pytest.fixture
def real_champion(
    tmp_path: Path, request: pytest.FixtureRequest
) -> Generator[ChampionModel, None, None]:
    """Train, register and promote a real LightGBM on a throwaway SQLite MLflow.

    Returns the ``ChampionModel`` that ``serving.load_champion`` would hand the
    API -- this exercises the exact ``mlflow.lightgbm.load_model`` + alias
    resolution chain apps/api's other tests replace with a double.
    """
    tracking_uri = f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"
    previous_tracking_uri = mlflow.get_tracking_uri()
    previous_registry_uri = mlflow.get_registry_uri()

    def _restore_mlflow_uris() -> None:
        mlflow.set_tracking_uri(previous_tracking_uri)
        mlflow.set_registry_uri(previous_registry_uri)

    request.addfinalizer(_restore_mlflow_uris)

    settings = _train_register_and_promote_champion(tracking_uri, tmp_path / "artifacts")
    # The load itself is the part of F3-18 serving no other apps/api test
    # touches: models:/<name>@<alias> -> mlflow.lightgbm.load_model.
    yield load_champion(settings)


def test_predictions_served_by_real_mlflow_champion(
    client: TestClient,
    auth_headers: dict[str, str],
    real_champion: ChampionModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/v1/predictions end-to-end against a real registered LightGBM."""
    monkeypatch.setitem(app.dependency_overrides, get_champion, lambda: real_champion)

    response = client.get(
        "/api/v1/predictions",
        params={"id_well": "POZO-001", "as_of_date": "2024-03-15", "horizon": 3},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()

    # Proves the real chain ran end to end: the registry's concrete version
    # answered, not the FAKE_MODEL_VERSION double from conftest.py.
    assert real_champion.version != FAKE_MODEL_VERSION
    assert real_champion.version.isdigit()  # a genuine MLflow registry version
    assert body["model_version"] == real_champion.version

    assert len(body["predictions"]) == 3
    assert [point["month"] for point in body["predictions"]] == [
        "2024-04-01",
        "2024-05-01",
        "2024-06-01",
    ]
    for point in body["predictions"]:
        oil_prod_m3 = point["oil_prod_m3"]
        assert isinstance(oil_prod_m3, float)
        assert math.isfinite(oil_prod_m3)
