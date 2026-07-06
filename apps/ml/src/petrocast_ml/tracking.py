"""MLflow experiment tracking for training runs (F3-14).

Records every baseline training run (F3-13) as an MLflow run under the
experiment frozen in contract C: fixed parameters, evaluation metrics, the
mandatory traceability tags (``as_of_date`` / ``features_version`` /
``git_commit``) and the model artifact. The pipeline stays pure — ``train()``
never touches MLflow; the offline CLI (``python -m petrocast_ml.training
--track``) is the single point that opens a run and hands the result here.

Consumers depend only on the ``TrackingClient`` port, so the logging mapping is
exercised with an in-memory double and needs no server (ADR-0032). The MLflow
adapter is validated separately against a local file store. Run names embed the
knowledge cutoff, so two cutoffs land as two runs the tracking UI tells apart.
"""

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

import mlflow
import mlflow.lightgbm
import pandas as pd

from petrocast_ml.config import MlSettings, get_settings
from petrocast_ml.evaluation.report import EvaluationReport
from petrocast_ml.training.contracts import TrainableModel, TrainingRequest, TrainingResult

TrackingValue = str | int | float | bool

#: Tag keys frozen by contract C — every training run must carry all three so a
#: registered model can be traced back to the data cutoff and the code that
#: produced it.
AS_OF_DATE_TAG = "as_of_date"
FEATURES_VERSION_TAG = "features_version"
GIT_COMMIT_TAG = "git_commit"

#: Tag set by F3-15: whether the run's candidate passed the blocking gates —
#: what champion promotion (#16) checks before touching the alias.
GATES_PASSED_TAG = "gates_passed"
MODEL_ARTIFACT_PATH = "model"
LOGGED_MODEL_URI_TAG = "logged_model_uri"


@dataclass(frozen=True, slots=True)
class RunMetadata:
    """Contract C traceability for a run: what data and code produced it."""

    as_of_date: date
    features_version: str
    git_commit: str


@runtime_checkable
class TrackingClient(Protocol):
    """Port for recording reproducible training runs."""

    def start_run(self, *, run_name: str) -> AbstractContextManager[Any]:
        """Open a run; the returned context manager closes it on exit."""
        ...

    def log_parameters(self, parameters: Mapping[str, TrackingValue]) -> None:
        """Record immutable run parameters."""
        ...

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        """Record evaluation metrics."""
        ...

    def set_tags(self, tags: Mapping[str, str]) -> None:
        """Record traceability tags for the run."""
        ...

    def log_artifacts(self, artifact_dir: Path) -> None:
        """Upload every file in a directory as run artifacts."""
        ...

    def log_model(self, model: TrainableModel) -> str:
        """Log a loadable MLflow model and return its immutable URI."""
        ...


class MlflowTrackingClient:
    """``TrackingClient`` backed by an MLflow tracking server or file store.

    Binds the fluent MLflow API to the configured tracking URI and experiment
    (contract C) on construction. Uses the process-global active run, which is
    all a single-origin training CLI needs; concurrent runs are out of scope.
    """

    def __init__(self, settings: MlSettings) -> None:
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        mlflow.set_experiment(settings.mlflow_experiment_name)

    def start_run(self, *, run_name: str) -> AbstractContextManager[Any]:
        return mlflow.start_run(run_name=run_name)

    def log_parameters(self, parameters: Mapping[str, TrackingValue]) -> None:
        mlflow.log_params(dict(parameters))

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        mlflow.log_metrics(dict(metrics))

    def set_tags(self, tags: Mapping[str, str]) -> None:
        mlflow.set_tags(dict(tags))

    def log_artifacts(self, artifact_dir: Path) -> None:
        mlflow.log_artifacts(str(artifact_dir))

    def log_model(self, model: TrainableModel) -> str:
        model_info = mlflow.lightgbm.log_model(model, name=MODEL_ARTIFACT_PATH)
        return cast(str, model_info.model_uri)


def create_tracking_client(settings: MlSettings | None = None) -> TrackingClient:
    """Create the MLflow-backed tracking client (contract C)."""
    return MlflowTrackingClient(settings or get_settings())


def _tracking_value(value: object) -> TrackingValue:
    """Coerce a parameter value to a loggable scalar (None, tuples → text)."""
    if isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _contract_c_tags(metadata: RunMetadata) -> dict[str, str]:
    return {
        AS_OF_DATE_TAG: metadata.as_of_date.isoformat(),
        FEATURES_VERSION_TAG: metadata.features_version,
        GIT_COMMIT_TAG: metadata.git_commit,
    }


def _run_parameters(
    request: TrainingRequest,
    result: TrainingResult,
    dataset: pd.DataFrame,
) -> dict[str, TrackingValue]:
    """Immutable run inputs: the effective model params plus request/dataset shape."""
    get_params = getattr(result.model, "get_params", None)
    if callable(get_params):
        model_params: Mapping[str, object] = get_params()
    else:
        model_params = cast(Mapping[str, object], getattr(result.model, "params", {}))
    parameters: dict[str, TrackingValue] = {
        f"lgbm_{name}": _tracking_value(value) for name, value in model_params.items()
    }
    parameters.update(
        horizon=request.horizon,
        validation_cutoffs=request.validation_cutoffs,
        dataset_rows=len(dataset),
        dataset_wells=int(dataset["well_id"].nunique()),
        dataset_cutoffs=int(dataset["as_of_date"].nunique()),
    )
    return parameters


def record_training_run(
    client: TrackingClient,
    *,
    request: TrainingRequest,
    result: TrainingResult,
    dataset: pd.DataFrame,
    run_metadata: RunMetadata,
    artifact_dir: Path,
    evaluation: EvaluationReport | None = None,
) -> str:
    """Log one training run (params, metrics, contract-C tags, artifacts).

    Opens a run named after the knowledge cutoff and horizon, records the
    effective model parameters and dataset footprint, the model/naive metrics
    of ``result``, the three mandatory traceability tags and the artifact
    directory produced by ``save_training_artifact`` (``model.txt`` +
    ``metadata.json``). When an evaluation ran (F3-15) its flat ``eval_*``
    metrics land on the same run plus the gate tag promotion (#16) reads.
    Returns the immutable MLflow run ID so downstream registry operations can
    register the exact candidate produced by this execution.
    """
    run_name = f"{run_metadata.as_of_date.isoformat()}-h{request.horizon}"
    with client.start_run(run_name=run_name) as active_run:
        run_id = getattr(getattr(active_run, "info", None), "run_id", None)
        if not isinstance(run_id, str) or not run_id:
            raise RuntimeError("tracking client did not expose an active MLflow run ID")
        client.set_tags(_contract_c_tags(run_metadata))
        client.log_parameters(_run_parameters(request, result, dataset))
        client.log_metrics(dict(result.metrics))
        if evaluation is not None:
            client.log_metrics(evaluation.to_mlflow_metrics())
            client.set_tags({GATES_PASSED_TAG: str(evaluation.gates_passed).lower()})
        client.log_artifacts(artifact_dir)
        client.set_tags({LOGGED_MODEL_URI_TAG: client.log_model(result.model)})
    return run_id


__all__ = [
    "AS_OF_DATE_TAG",
    "FEATURES_VERSION_TAG",
    "GATES_PASSED_TAG",
    "GIT_COMMIT_TAG",
    "LOGGED_MODEL_URI_TAG",
    "MODEL_ARTIFACT_PATH",
    "MlflowTrackingClient",
    "RunMetadata",
    "TrackingClient",
    "TrackingValue",
    "create_tracking_client",
    "record_training_run",
]
