"""CLI smoke: registry subcommands against a real MLflow SQLite store (F3-16).

Exercises ``python -m petrocast_ml.registry`` end to end via subprocess —
register an approved candidate, inspect it, promote the ``champion`` alias and
roll it back — plus the failure contract (exit 1 with a JSON ``{"error": ...}``
payload when promoting a version that does not exist). The registry needs a
database-backed store for aliases, so this mirrors the offline SQLite setup in
``test_registry_mlflow.py`` and the subprocess + env pattern in
``test_evaluation_cli.py``. The CLI reads its target store from the
environment (``MLFLOW_TRACKING_URI`` + the ``PETROCAST_MLFLOW_*`` settings).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import mlflow
import pytest
from mlflow.tracking import MlflowClient

from petrocast_ml.tracking import AS_OF_DATE_TAG, GATES_PASSED_TAG, LOGGED_MODEL_URI_TAG

MODEL_NAME = "f3-16-registry-cli-smoke"


def _seed_approved_run(
    writer: MlflowClient,
    experiment_id: str,
    scratch: Path,
    *,
    tag: str,
    gates_passed: bool = True,
) -> str:
    """Create a terminated run carrying every tag promotion metadata needs."""
    run_id = writer.create_run(experiment_id).info.run_id
    writer.set_tag(run_id, AS_OF_DATE_TAG, "2026-01-01")
    writer.set_tag(run_id, GATES_PASSED_TAG, "true" if gates_passed else "false")
    writer.log_metric(run_id, "eval_model_mae_m3", 8.5)
    writer.log_metric(run_id, "eval_naive_mae_m3", 10.0)
    model_file = scratch / f"MLmodel-{tag}"
    model_file.write_text("offline registry cli smoke", encoding="utf-8")
    logged_model = writer.create_logged_model(experiment_id, name=tag, source_run_id=run_id)
    writer.log_model_artifact(logged_model.model_id, str(model_file))
    writer.finalize_logged_model(logged_model.model_id, "READY")
    writer.set_tag(run_id, LOGGED_MODEL_URI_TAG, f"models:/{logged_model.model_id}")
    writer.set_terminated(run_id)
    return run_id


def _run_cli(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "petrocast_ml.registry", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


@pytest.fixture
def registry_cli_store(
    tmp_path: Path, request: pytest.FixtureRequest
) -> tuple[MlflowClient, str, Path, dict[str, str]]:
    """A temp SQLite tracking/registry store plus the env the CLI reads."""
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
    writer = MlflowClient(tracking_uri=tracking_uri)
    experiment_id = writer.create_experiment(
        "f3-16-registry-cli-smoke", artifact_location=artifact_root.as_uri()
    )
    env = {
        **os.environ,
        "MLFLOW_TRACKING_URI": tracking_uri,
        "PETROCAST_MLFLOW_MODEL_NAME": MODEL_NAME,
        "PETROCAST_MLFLOW_MODEL_ALIAS": "champion",
    }
    return writer, experiment_id, tmp_path, env


def test_cli_register_inspect_promote_and_rollback(
    registry_cli_store: tuple[MlflowClient, str, Path, dict[str, str]],
) -> None:
    writer, experiment_id, scratch, env = registry_cli_store
    first_run = _seed_approved_run(writer, experiment_id, scratch, tag="first")
    second_run = _seed_approved_run(writer, experiment_id, scratch, tag="second")

    registered_first = _run_cli(["register", "--run-id", first_run], env)
    assert registered_first.returncode == 0, registered_first.stderr
    assert json.loads(registered_first.stdout)["version"] == "1"

    registered_second = _run_cli(["register", "--run-id", second_run], env)
    assert registered_second.returncode == 0, registered_second.stderr
    assert json.loads(registered_second.stdout)["version"] == "2"

    inspected = _run_cli(["inspect", "--version", "2"], env)
    assert inspected.returncode == 0, inspected.stderr
    inspected_payload = json.loads(inspected.stdout)
    assert inspected_payload["run_id"] == second_run
    assert inspected_payload["as_of_date"] == "2026-01-01"
    assert inspected_payload["gates_passed"] is True

    promoted = _run_cli(["promote", "--version", "2"], env)
    assert promoted.returncode == 0, promoted.stderr
    assert json.loads(promoted.stdout)["version"] == "2"

    champion = _run_cli(["inspect"], env)
    assert champion.returncode == 0, champion.stderr
    assert json.loads(champion.stdout)["version"] == "2"

    rolled_back = _run_cli(["rollback", "--to-version", "1"], env)
    assert rolled_back.returncode == 0, rolled_back.stderr
    assert json.loads(rolled_back.stdout)["version"] == "1"

    champion_after_rollback = _run_cli(["inspect"], env)
    assert champion_after_rollback.returncode == 0, champion_after_rollback.stderr
    assert json.loads(champion_after_rollback.stdout)["version"] == "1"


def test_cli_promote_missing_version_exits_1_with_error_payload(
    registry_cli_store: tuple[MlflowClient, str, Path, dict[str, str]],
) -> None:
    writer, experiment_id, scratch, env = registry_cli_store
    approved_run = _seed_approved_run(writer, experiment_id, scratch, tag="only")

    registered = _run_cli(["register", "--run-id", approved_run], env)
    assert registered.returncode == 0, registered.stderr

    failed = _run_cli(["promote", "--version", "999"], env)
    assert failed.returncode == 1, failed.stderr
    assert "error" in json.loads(failed.stdout)
