"""Logging contract of a training run (F3-14), exercised with an in-memory double.

``record_training_run`` maps a training result onto the ``TrackingClient`` port:
the three mandatory contract-C tags, the effective model params plus dataset
footprint, the model/naive metrics and the artifact directory — all inside a
single opened-and-closed run whose name embeds the cutoff. No MLflow server is
needed; the adapter itself is checked in ``smoke/test_tracking_mlflow.py``.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from petrocast_ml.evaluation import EvaluationReport, GateThresholds
from petrocast_ml.evaluation.gates import evaluate_gates
from petrocast_ml.tracking import (
    AS_OF_DATE_TAG,
    FEATURES_VERSION_TAG,
    GATES_PASSED_TAG,
    GIT_COMMIT_TAG,
    LOGGED_MODEL_URI_TAG,
    RunMetadata,
    TrackingClient,
    TrackingValue,
    record_training_run,
)
from petrocast_ml.training import (
    MODEL_FILE,
    TARGET_COLUMN,
    TrainingRequest,
    TrainingResult,
    build_training_dataset,
    save_training_artifact,
    train,
)

#: Tiny overrides so the run trains on ~a dozen rows in <1s (mirrors F3-13 smoke).
SMOKE_PARAMS = {"n_estimators": 10, "min_child_samples": 1, "num_leaves": 4}


class FakeTrackingClient:
    """In-memory ``TrackingClient`` capturing everything a run logs."""

    def __init__(self) -> None:
        self.run_names: list[str] = []
        self.started = 0
        self.ended = 0
        self.parameters: dict[str, TrackingValue] = {}
        self.metrics: dict[str, float] = {}
        self.tags: dict[str, str] = {}
        self.artifact_dirs: list[Path] = []
        self.models: list[object] = []

    @contextmanager
    def start_run(self, *, run_name: str) -> Iterator[object]:
        self.run_names.append(run_name)
        self.started += 1
        try:
            yield _FakeActiveRun(info=_FakeRunInfo(run_id=f"run-{self.started}"))
        finally:
            self.ended += 1

    def log_parameters(self, parameters: Mapping[str, TrackingValue]) -> None:
        self.parameters.update(parameters)

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        self.metrics.update(metrics)

    def set_tags(self, tags: Mapping[str, str]) -> None:
        self.tags.update(tags)

    def log_artifacts(self, artifact_dir: Path) -> None:
        self.artifact_dirs.append(artifact_dir)

    def log_model(self, model: object) -> str:
        self.models.append(model)
        return "models:/m-fixture"


@dataclass(frozen=True, slots=True)
class _FakeRunInfo:
    run_id: str


@dataclass(frozen=True, slots=True)
class _FakeActiveRun:
    info: _FakeRunInfo


@pytest.fixture
def dataset(production_monthly: pd.DataFrame, well_features: pd.DataFrame) -> pd.DataFrame:
    return build_training_dataset(well_features, production_monthly, horizons=(1, 2, 3))


@pytest.fixture
def request_smoke() -> TrainingRequest:
    return TrainingRequest(as_of_date=date(2026, 1, 1), features_version="fixtures", horizon=3)


@pytest.fixture
def result(dataset: pd.DataFrame, request_smoke: TrainingRequest) -> TrainingResult:
    return train(dataset, dataset[TARGET_COLUMN], request=request_smoke, params=SMOKE_PARAMS)


@pytest.fixture
def artifact_dir(
    result: TrainingResult,
    request_smoke: TrainingRequest,
    dataset: pd.DataFrame,
    tmp_path: Path,
) -> Path:
    return save_training_artifact(
        result, request=request_smoke, dataset=dataset, output_dir=tmp_path / "artifact"
    )


@pytest.fixture
def run_metadata() -> RunMetadata:
    return RunMetadata(
        as_of_date=date(2026, 1, 1), features_version="fixtures", git_commit="abc123"
    )


def test_fake_client_conforms_to_the_port() -> None:
    assert isinstance(FakeTrackingClient(), TrackingClient)


def test_records_the_mandatory_contract_c_tags(
    result: TrainingResult,
    request_smoke: TrainingRequest,
    dataset: pd.DataFrame,
    artifact_dir: Path,
    run_metadata: RunMetadata,
) -> None:
    fake = FakeTrackingClient()
    run_id = record_training_run(
        fake,
        request=request_smoke,
        result=result,
        dataset=dataset,
        run_metadata=run_metadata,
        artifact_dir=artifact_dir,
    )
    assert fake.tags == {
        AS_OF_DATE_TAG: "2026-01-01",
        FEATURES_VERSION_TAG: "fixtures",
        GIT_COMMIT_TAG: "abc123",
        LOGGED_MODEL_URI_TAG: "models:/m-fixture",
    }
    assert run_id == "run-1"


def test_logs_effective_params_and_dataset_footprint(
    result: TrainingResult,
    request_smoke: TrainingRequest,
    dataset: pd.DataFrame,
    artifact_dir: Path,
    run_metadata: RunMetadata,
) -> None:
    fake = FakeTrackingClient()
    record_training_run(
        fake,
        request=request_smoke,
        result=result,
        dataset=dataset,
        run_metadata=run_metadata,
        artifact_dir=artifact_dir,
    )
    # The effective (overridden) model params are logged, not just the defaults.
    assert fake.parameters["lgbm_n_estimators"] == 10
    assert fake.parameters["horizon"] == 3
    assert fake.parameters["validation_cutoffs"] == 0
    assert fake.parameters["dataset_rows"] == len(dataset)
    assert fake.parameters["dataset_wells"] == dataset["well_id"].nunique()
    assert fake.parameters["dataset_cutoffs"] == dataset["as_of_date"].nunique()


def test_logs_model_and_naive_metrics(
    result: TrainingResult,
    request_smoke: TrainingRequest,
    dataset: pd.DataFrame,
    artifact_dir: Path,
    run_metadata: RunMetadata,
) -> None:
    fake = FakeTrackingClient()
    record_training_run(
        fake,
        request=request_smoke,
        result=result,
        dataset=dataset,
        run_metadata=run_metadata,
        artifact_dir=artifact_dir,
    )
    assert fake.metrics == dict(result.metrics)
    for key in ("model_mae_m3", "model_rmse_m3", "naive_mae_m3", "naive_rmse_m3"):
        assert key in fake.metrics


def test_logs_the_artifact_directory(
    result: TrainingResult,
    request_smoke: TrainingRequest,
    dataset: pd.DataFrame,
    artifact_dir: Path,
    run_metadata: RunMetadata,
) -> None:
    fake = FakeTrackingClient()
    record_training_run(
        fake,
        request=request_smoke,
        result=result,
        dataset=dataset,
        run_metadata=run_metadata,
        artifact_dir=artifact_dir,
    )
    assert fake.artifact_dirs == [artifact_dir]
    assert (artifact_dir / MODEL_FILE).exists()
    assert fake.models == [result.model]


def test_opens_and_closes_exactly_one_run(
    result: TrainingResult,
    request_smoke: TrainingRequest,
    dataset: pd.DataFrame,
    artifact_dir: Path,
    run_metadata: RunMetadata,
) -> None:
    fake = FakeTrackingClient()
    record_training_run(
        fake,
        request=request_smoke,
        result=result,
        dataset=dataset,
        run_metadata=run_metadata,
        artifact_dir=artifact_dir,
    )
    assert fake.started == 1
    assert fake.ended == 1


def test_run_name_distinguishes_two_cutoffs(
    result: TrainingResult,
    request_smoke: TrainingRequest,
    dataset: pd.DataFrame,
    artifact_dir: Path,
) -> None:
    """Two cutoffs land as two differently named runs (AC: distinguishable runs)."""
    fake = FakeTrackingClient()
    for as_of in (date(2026, 1, 1), date(2025, 12, 1)):
        record_training_run(
            fake,
            request=request_smoke,
            result=result,
            dataset=dataset,
            run_metadata=RunMetadata(
                as_of_date=as_of, features_version="fixtures", git_commit="abc123"
            ),
            artifact_dir=artifact_dir,
        )
    assert fake.run_names == ["2026-01-01-h3", "2025-12-01-h3"]
    assert len(set(fake.run_names)) == 2


def _evaluation_report(*, passed: bool) -> EvaluationReport:
    gates = evaluate_gates(
        mase_median=0.8 if passed else 1.4,
        naive_mae_ratio=0.9 if passed else 1.5,
        arps_mape_gap_pp=None,
        thresholds=GateThresholds(),
    )
    return EvaluationReport(
        as_of_date=date(2026, 1, 1),
        horizons=(1, 2, 3),
        thresholds=GateThresholds(),
        wells_in_test=4,
        wells_eligible=3,
        wells_excluded_short_history=1,
        wells_mase_undefined=0,
        arps_fitted_wells=0,
        arps_failed_wells=3,
        arps_degraded=True,
        model_mae_m3=10.0,
        naive_mae_m3=12.0,
        distributions={"mase": {"p50": 0.8, "p75": 1.0, "p90": 1.2}},
        gates=gates,
        gates_passed=passed,
    )


def test_records_evaluation_metrics_and_gate_tag(
    result: TrainingResult,
    request_smoke: TrainingRequest,
    dataset: pd.DataFrame,
    artifact_dir: Path,
    run_metadata: RunMetadata,
) -> None:
    fake = FakeTrackingClient()
    record_training_run(
        fake,
        request=request_smoke,
        result=result,
        dataset=dataset,
        run_metadata=run_metadata,
        artifact_dir=artifact_dir,
        evaluation=_evaluation_report(passed=False),
    )
    assert fake.metrics["eval_gates_passed"] == 0.0
    assert fake.metrics["eval_mase_p50"] == 0.8
    assert fake.tags[GATES_PASSED_TAG] == "false"


def test_run_without_evaluation_logs_no_eval_keys(
    result: TrainingResult,
    request_smoke: TrainingRequest,
    dataset: pd.DataFrame,
    artifact_dir: Path,
    run_metadata: RunMetadata,
) -> None:
    fake = FakeTrackingClient()
    record_training_run(
        fake,
        request=request_smoke,
        result=result,
        dataset=dataset,
        run_metadata=run_metadata,
        artifact_dir=artifact_dir,
    )
    assert not any(key.startswith("eval_") for key in fake.metrics)
    assert GATES_PASSED_TAG not in fake.tags
