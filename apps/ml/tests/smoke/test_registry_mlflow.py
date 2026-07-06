"""Offline MLflow registry round-trip against SQLite and file artifacts."""

from datetime import date
from pathlib import Path

import mlflow
import pytest
from mlflow.tracking import MlflowClient

from petrocast_ml import MlSettings
from petrocast_ml.registry import (
    MlflowModelRegistry,
    create_registry_client,
    promote_champion,
    register_candidate,
)
from petrocast_ml.tracking import AS_OF_DATE_TAG, GATES_PASSED_TAG, LOGGED_MODEL_URI_TAG

MODEL_NAME = "f3-16-registry-smoke"


def test_mlflow_registry_registers_promotes_and_resolves_champion(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
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
    artifact_root = tmp_path / "artifacts"
    settings = MlSettings(
        mlflow_tracking_uri=tracking_uri,
        mlflow_artifact_root=artifact_root.as_uri(),
        mlflow_experiment_name="f3-16-registry-smoke",
        mlflow_model_name=MODEL_NAME,
        mlflow_model_alias="champion",
    )
    writer = MlflowClient(tracking_uri=tracking_uri)
    experiment_id = writer.create_experiment(
        settings.mlflow_experiment_name,
        artifact_location=artifact_root.as_uri(),
    )
    run = writer.create_run(experiment_id)
    run_id = run.info.run_id
    writer.set_tag(run_id, AS_OF_DATE_TAG, "2026-01-01")
    writer.set_tag(run_id, GATES_PASSED_TAG, "true")
    writer.log_metric(run_id, "eval_model_mae_m3", 8.5)
    writer.log_metric(run_id, "eval_naive_mae_m3", 10.0)
    model_file = tmp_path / "MLmodel"
    model_file.write_text("offline registry smoke", encoding="utf-8")
    logged_model = writer.create_logged_model(
        experiment_id,
        name="model",
        source_run_id=run_id,
    )
    writer.log_model_artifact(logged_model.model_id, str(model_file))
    writer.finalize_logged_model(logged_model.model_id, "READY")
    model_uri = f"models:/{logged_model.model_id}"
    writer.set_tag(run_id, LOGGED_MODEL_URI_TAG, model_uri)
    writer.set_terminated(run_id)

    registry = create_registry_client(settings)
    assert isinstance(registry, MlflowModelRegistry)

    candidate = register_candidate(registry, run_id=run_id, settings=settings)
    promoted = promote_champion(registry, version=candidate.version, settings=settings)

    assert candidate.name == MODEL_NAME
    assert candidate.version == "1"
    assert candidate.source == model_uri
    assert candidate.run_id == run_id
    assert candidate.as_of_date == date(2026, 1, 1)
    assert candidate.metrics["eval_model_mae_m3"] == pytest.approx(8.5)
    assert candidate.metrics["eval_naive_mae_m3"] == pytest.approx(10.0)
    assert candidate.gates_passed is True
    assert promoted == candidate

    reader = MlflowClient(tracking_uri=tracking_uri)
    registered = reader.get_model_version(MODEL_NAME, candidate.version)
    champion = reader.get_model_version_by_alias(MODEL_NAME, "champion")
    assert registered.run_id == run_id
    assert registered.source == candidate.source
    assert str(champion.version) == candidate.version
    assert registry.get_by_alias(name=MODEL_NAME, alias="champion") == candidate
