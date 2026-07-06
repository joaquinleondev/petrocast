"""Offline MLflow registry round-trip against SQLite and file artifacts."""

from datetime import date
from pathlib import Path

import mlflow
import pytest
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from petrocast_ml import MlSettings
from petrocast_ml.registry import (
    CandidateNotApprovedError,
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


def _seed_candidate_run(
    writer: MlflowClient,
    experiment_id: str,
    scratch: Path,
    *,
    tag: str,
    gates_passed: bool,
) -> str:
    """Seed a terminated run with the tags and logged model registration needs."""
    run_id = writer.create_run(experiment_id).info.run_id
    writer.set_tag(run_id, AS_OF_DATE_TAG, "2026-01-01")
    writer.set_tag(run_id, GATES_PASSED_TAG, "true" if gates_passed else "false")
    writer.log_metric(run_id, "eval_model_mae_m3", 8.5)
    writer.log_metric(run_id, "eval_naive_mae_m3", 10.0)
    model_file = scratch / f"MLmodel-{tag}"
    model_file.write_text("offline registry smoke", encoding="utf-8")
    logged_model = writer.create_logged_model(experiment_id, name=tag, source_run_id=run_id)
    writer.log_model_artifact(logged_model.model_id, str(model_file))
    writer.finalize_logged_model(logged_model.model_id, "READY")
    writer.set_tag(run_id, LOGGED_MODEL_URI_TAG, f"models:/{logged_model.model_id}")
    writer.set_terminated(run_id)
    return run_id


def test_mlflow_registry_blocks_failed_gate_and_supports_rollback(
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
        settings.mlflow_experiment_name, artifact_location=artifact_root.as_uri()
    )
    first_run = _seed_candidate_run(writer, experiment_id, tmp_path, tag="first", gates_passed=True)
    second_run = _seed_candidate_run(
        writer, experiment_id, tmp_path, tag="second", gates_passed=True
    )
    rejected_run = _seed_candidate_run(
        writer, experiment_id, tmp_path, tag="rejected", gates_passed=False
    )

    registry = create_registry_client(settings)
    first = register_candidate(registry, run_id=first_run, settings=settings)
    second = register_candidate(registry, run_id=second_run, settings=settings)
    rejected = register_candidate(registry, run_id=rejected_run, settings=settings)
    assert rejected.gates_passed is False

    reader = MlflowClient(tracking_uri=tracking_uri)
    # A candidate that failed the blocking gates must never move the alias.
    with pytest.raises(CandidateNotApprovedError):
        promote_champion(registry, version=rejected.version, settings=settings)
    with pytest.raises(MlflowException):
        reader.get_model_version_by_alias(MODEL_NAME, "champion")

    # Rollback is a re-promotion: move the alias forward, then back to the prior version.
    promote_champion(registry, version=first.version, settings=settings)
    promote_champion(registry, version=second.version, settings=settings)
    assert str(reader.get_model_version_by_alias(MODEL_NAME, "champion").version) == second.version

    rolled_back = promote_champion(registry, version=first.version, settings=settings)
    assert rolled_back == first
    assert str(reader.get_model_version_by_alias(MODEL_NAME, "champion").version) == first.version
    assert registry.get_by_alias(name=MODEL_NAME, alias="champion") == first
