"""MLflow adapter check against a local file store (F3-14): no server, no net.

Proves the fluent-API adapter really persists a run — params, metrics, the
contract-C tags and the ``model.txt`` / ``metadata.json`` artifacts — by
logging into a temp file store and reading it back through ``MlflowClient``.
The logging mapping itself is covered exhaustively (with a double) in
``unit/test_tracking.py``; this only guards the real MLflow round-trip.
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from mlflow.tracking import MlflowClient

from petrocast_ml import MlSettings
from petrocast_ml.tracking import (
    AS_OF_DATE_TAG,
    FEATURES_VERSION_TAG,
    GIT_COMMIT_TAG,
    LOGGED_MODEL_URI_TAG,
    MlflowTrackingClient,
    RunMetadata,
    create_tracking_client,
    record_training_run,
)
from petrocast_ml.training import (
    METADATA_FILE,
    MODEL_FILE,
    TARGET_COLUMN,
    TrainingRequest,
    build_training_dataset,
    save_training_artifact,
    train,
)

SMOKE_PARAMS = {"n_estimators": 10, "min_child_samples": 1, "num_leaves": 4}
EXPERIMENT_NAME = "f3-14-tracking-smoke"


def test_mlflow_client_persists_run_to_file_store(
    production_monthly: pd.DataFrame,
    well_features: pd.DataFrame,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The local file store is in maintenance mode in mlflow 3.14 and gated behind
    # an explicit opt-in; it keeps this smoke fully offline (prod points
    # MLFLOW_TRACKING_URI at the Postgres-backed server).
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    store = tmp_path / "mlruns"
    tracking_uri = store.as_uri()
    settings = MlSettings(
        mlflow_tracking_uri=tracking_uri,
        mlflow_experiment_name=EXPERIMENT_NAME,
    )
    dataset = build_training_dataset(well_features, production_monthly, horizons=(1, 2, 3))
    request = TrainingRequest(as_of_date=date(2026, 1, 1), features_version="fixtures", horizon=3)
    result = train(dataset, dataset[TARGET_COLUMN], request=request, params=SMOKE_PARAMS)
    artifact_dir = save_training_artifact(
        result, request=request, dataset=dataset, output_dir=tmp_path / "artifact"
    )
    run_metadata = RunMetadata(
        as_of_date=date(2026, 1, 1), features_version="fixtures", git_commit="abc123"
    )

    client = create_tracking_client(settings)
    assert isinstance(client, MlflowTrackingClient)
    run_id = record_training_run(
        client,
        request=request,
        result=result,
        dataset=dataset,
        run_metadata=run_metadata,
        artifact_dir=artifact_dir,
    )

    reader = MlflowClient(tracking_uri=tracking_uri)
    experiment = reader.get_experiment_by_name(EXPERIMENT_NAME)
    assert experiment is not None
    runs = reader.search_runs([experiment.experiment_id])
    assert len(runs) == 1
    run = runs[0]

    assert run.data.tags[AS_OF_DATE_TAG] == "2026-01-01"
    assert run.data.tags[FEATURES_VERSION_TAG] == "fixtures"
    assert run.data.tags[GIT_COMMIT_TAG] == "abc123"
    assert run.info.run_id == run_id
    assert run.data.tags["mlflow.runName"] == "2026-01-01-h3"
    assert run.data.tags[LOGGED_MODEL_URI_TAG].startswith("models:/m-")

    assert run.data.metrics["model_mae_m3"] == pytest.approx(result.metrics["model_mae_m3"])
    assert run.data.params["horizon"] == "3"
    assert run.data.params["dataset_rows"] == str(len(dataset))
    assert run.data.params["lgbm_n_estimators"] == "10"

    artifacts = {item.path for item in reader.list_artifacts(run.info.run_id)}
    assert {MODEL_FILE, METADATA_FILE} <= artifacts
    logged_models = reader.search_logged_models([experiment.experiment_id])
    assert len(logged_models) == 1
    assert f"models:/{logged_models[0].model_id}" == run.data.tags[LOGGED_MODEL_URI_TAG]
