"""Offline end-to-end inference smoke: real champion round-trip (F3-23).

apps/ml already validates every piece in isolation: train+log
(``test_tracking_mlflow.py``), register/promote/alias round-trip with a
text-file stand-in model (``test_registry_mlflow.py``) and ``predict()`` with
doubles (``unit/test_inference.py``). None of them loads a *real* model back
through ``models:/<name>@champion``. This smoke chains the full pipeline CI
must guarantee: train -> evaluate -> track -> register -> promote ->
``load_champion`` -> contract-A features -> ``predict``, all against a
throwaway SQLite-backed MLflow (registry aliases need a DB-backed store) with
file artifacts -- no server, no Postgres, no network.

The gate verdict of the tiny smoke model on fixtures is data-dependent (see
``test_evaluation_cli.py``), so the happy path runs the real ``evaluate()``
wiring with explicitly permissive thresholds: what it pins down is the
mechanism (report -> ``gates_passed`` tag -> promotion check), not the model's
quality. Feature-contract violations are covered by
``unit/test_feature_contract.py``; here the feature row is consumed through
``validate_feature_frame`` exactly like serving does, so contract drift also
breaks this smoke.
"""

import math
from datetime import date
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import pytest
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from petrocast_ml import (
    MlSettings,
    RunMetadata,
    create_registry_client,
    create_tracking_client,
    load_champion,
    predict,
    promote_champion,
    record_training_run,
    register_candidate,
    validate_feature_frame,
)
from petrocast_ml.evaluation import GateThresholds, evaluate
from petrocast_ml.training import (
    TARGET_COLUMN,
    TrainingRequest,
    build_training_dataset,
    save_training_artifact,
    train,
)

MODEL_NAME = "f3-23-inference-smoke"
AS_OF_DATE = date(2026, 1, 1)
HORIZONS = (1, 2, 3)

# Tiny/deterministic: the smoke proves the pipeline loads and serves a *real*
# LightGBM, not that the forecast is accurate (same params as the tracking smoke).
SMOKE_PARAMS = {"n_estimators": 10, "min_child_samples": 1, "num_leaves": 4}


def _local_mlflow_settings(tmp_path: Path, request: pytest.FixtureRequest) -> MlSettings:
    """Point mlflow's process-global URIs at a throwaway SQLite store.

    Mirrors ``test_registry_mlflow.py``: aliases need a database-backed store,
    and the global tracking/registry URIs are restored on teardown so other
    tests never observe the temporary store.
    """
    database = tmp_path / "mlflow.db"
    tracking_uri = f"sqlite:///{database.as_posix()}"
    previous_tracking_uri = mlflow.get_tracking_uri()
    previous_registry_uri = mlflow.get_registry_uri()
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_registry_uri(tracking_uri)

    def restore_mlflow_uris() -> None:
        mlflow.set_tracking_uri(previous_tracking_uri)
        mlflow.set_registry_uri(previous_registry_uri)

    request.addfinalizer(restore_mlflow_uris)
    return MlSettings(
        _env_file=None,
        mlflow_tracking_uri=tracking_uri,
        mlflow_artifact_root=(tmp_path / "artifacts").as_uri(),
        mlflow_experiment_name=MODEL_NAME,
        mlflow_model_name=MODEL_NAME,
        mlflow_model_alias="champion",
    )


def test_champion_round_trip_serves_usable_predictions(
    production_monthly: pd.DataFrame,
    well_features: pd.DataFrame,
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    settings = _local_mlflow_settings(tmp_path, request)
    # Pre-create the experiment with an explicit artifact_location: otherwise
    # MlflowTrackingClient creates it lazily with mlflow's default artifact
    # root, which lands outside tmp_path.
    MlflowClient(tracking_uri=settings.mlflow_tracking_uri).create_experiment(
        settings.mlflow_experiment_name, artifact_location=settings.mlflow_artifact_root
    )

    dataset = build_training_dataset(well_features, production_monthly, horizons=HORIZONS)
    training_request = TrainingRequest(
        as_of_date=AS_OF_DATE, features_version="ci-smoke", horizon=max(HORIZONS)
    )
    result = train(dataset, dataset[TARGET_COLUMN], request=training_request, params=SMOKE_PARAMS)
    artifact_dir = save_training_artifact(
        result, request=training_request, dataset=dataset, output_dir=tmp_path / "artifact"
    )

    report = evaluate(
        result.model,
        dataset,
        production_monthly,
        request=training_request,
        thresholds=GateThresholds(mase_median_max=math.inf, naive_mae_ratio_max=math.inf),
    )
    assert report.gates_passed is True

    run_id = record_training_run(
        create_tracking_client(settings),
        request=training_request,
        result=result,
        dataset=dataset,
        run_metadata=RunMetadata(
            as_of_date=AS_OF_DATE, features_version="ci-smoke", git_commit="f3-23-smoke"
        ),
        artifact_dir=artifact_dir,
        evaluation=report,
    )

    registry = create_registry_client(settings)
    candidate = register_candidate(registry, run_id=run_id, settings=settings)
    promote_champion(registry, version=candidate.version, settings=settings)

    # The load CI must guarantee: models:/<name>@champion -> a real LightGBM.
    champion = load_champion(settings)
    assert champion.uri == settings.champion_model_uri
    assert champion.version == candidate.version
    assert champion.version.isdigit()

    # Consume the feature row through the same contract gate serving uses.
    validated = validate_feature_frame(well_features)
    feature_row = validated.loc[
        (validated["well_id"] == "70001") & (validated["as_of_date"] == pd.Timestamp(AS_OF_DATE))
    ]
    assert len(feature_row) == 1, "fixture drifted: expected one 70001 row at the smoke cutoff"

    predictions = predict(champion.model, feature_row, horizon=max(HORIZONS))
    assert predictions.shape == (max(HORIZONS),)
    assert predictions.dtype == np.float64
    assert np.isfinite(predictions).all()

    # The version served is byte-for-byte the artifact that was promoted: the
    # loaded model must forecast exactly like the in-memory model it came from.
    in_memory_predictions = predict(result.model, feature_row, horizon=max(HORIZONS))
    assert np.allclose(predictions, in_memory_predictions)


def test_load_champion_fails_loudly_when_no_champion_exists(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """A missing champion must fail the pipeline, never degrade silently."""
    settings = _local_mlflow_settings(tmp_path, request)

    with pytest.raises(MlflowException):
        load_champion(settings)
