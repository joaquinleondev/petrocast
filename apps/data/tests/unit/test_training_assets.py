"""Offline contracts for the F3-19 retraining assets and schedule."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import cast

import dagster as dg
import pytest
from petrocast_ml.registry import CandidateNotApprovedError, ModelVersion

from petrocast_data.assets.features import (
    FEATURE_ASSET_KEY,
    FEATURE_MONTHLY_PARTITIONS,
    feature_dbt_assets,
)
from petrocast_data.assets.training import (
    EVALUATION_ASSET_KEY,
    PROMOTION_ASSET_KEY,
    RETRAINING_RETRY_POLICY,
    TRAINING_ASSET_KEY,
    EvaluatedCandidate,
    PromotionResult,
    ml_champion_promotion,
    ml_model_evaluation,
    ml_training_candidate,
    register_and_promote_candidate,
    retraining_job,
)
from petrocast_data.schedules import retraining_run_request, retraining_schedule
from petrocast_data.settings import DataSettings


class FakeRegistry:
    """Small registry double that records alias mutations."""

    def __init__(self, *, gates_passed: bool) -> None:
        self.gates_passed = gates_passed
        self.versions: dict[tuple[str, str], ModelVersion] = {}
        self.aliases: dict[tuple[str, str], str] = {}
        self.alias_calls: list[tuple[str, str, str]] = []

    def add_version(self, version: ModelVersion) -> None:
        self.versions[(version.name, version.version)] = version

    def register_candidate(
        self,
        *,
        name: str,
        run_id: str,
        source: str | None = None,
    ) -> ModelVersion:
        version = ModelVersion(
            name=name,
            version=str(len(self.versions) + 1),
            source=source or f"runs:/{run_id}/model",
            run_id=run_id,
            as_of_date=date(2026, 6, 1),
            metrics={"eval_model_mae_m3": 8.0},
            gates_passed=self.gates_passed,
        )
        self.add_version(version)
        return version

    def get_version(self, *, name: str, version: str) -> ModelVersion:
        return self.versions[(name, version)]

    def get_by_alias(self, *, name: str, alias: str) -> ModelVersion:
        return self.get_version(name=name, version=self.aliases[(name, alias)])

    def set_alias(self, *, name: str, alias: str, version: str) -> None:
        self.alias_calls.append((name, alias, version))
        self.aliases[(name, alias)] = version


def _settings() -> DataSettings:
    return cast(
        DataSettings,
        SimpleNamespace(
            mlflow_tracking_uri="sqlite:///offline.db",
            mlflow_experiment_name="f3-19-offline",
            mlflow_model_name="petrocast-test",
            mlflow_model_alias="champion",
        ),
    )


def _candidate(*, gates_passed: bool) -> EvaluatedCandidate:
    return EvaluatedCandidate(
        run_id="run-candidate",
        as_of_date=date(2026, 6, 1),
        gates_passed=gates_passed,
        metrics={"eval_model_mae_m3": 8.0},
    )


def test_training_assets_share_partitions_and_dependency_chain() -> None:
    assert ml_training_candidate.partitions_def == FEATURE_MONTHLY_PARTITIONS
    assert ml_model_evaluation.partitions_def == FEATURE_MONTHLY_PARTITIONS
    assert ml_champion_promotion.partitions_def == FEATURE_MONTHLY_PARTITIONS
    assert ml_training_candidate.asset_deps[TRAINING_ASSET_KEY] == {FEATURE_ASSET_KEY}
    assert ml_model_evaluation.asset_deps[EVALUATION_ASSET_KEY] == {TRAINING_ASSET_KEY}
    assert ml_champion_promotion.asset_deps[PROMOTION_ASSET_KEY] == {EVALUATION_ASSET_KEY}


def test_retraining_job_selects_the_full_chain() -> None:
    definitions = dg.Definitions(
        assets=[
            feature_dbt_assets,
            ml_training_candidate,
            ml_model_evaluation,
            ml_champion_promotion,
        ],
        jobs=[retraining_job],
        resources={"dbt": dg.ResourceDefinition.mock_resource()},
    )
    job = definitions.resolve_job_def("retraining_job")
    assert job.partitions_def == FEATURE_MONTHLY_PARTITIONS
    assert retraining_job.selection.resolve(definitions.resolve_asset_graph()) == {
        FEATURE_ASSET_KEY,
        TRAINING_ASSET_KEY,
        EVALUATION_ASSET_KEY,
        PROMOTION_ASSET_KEY,
    }


def test_monthly_schedule_builds_idempotent_partition_request() -> None:
    context = dg.build_schedule_context(
        scheduled_execution_time=datetime(2026, 7, 5, 6, tzinfo=UTC)
    )
    request = retraining_run_request(context)

    assert retraining_schedule.cron_schedule == "0 6 5 * *"
    assert retraining_schedule.execution_timezone == "UTC"
    assert retraining_schedule.job_name == "retraining_job"
    assert request.partition_key == "2026-07-01"
    assert request.run_key == "retraining:2026-07-01"
    assert request.tags == {
        "as_of_date": "2026-07-01",
        "petrocast/trigger": "schedule",
    }


def test_approved_candidate_moves_champion() -> None:
    registry = FakeRegistry(gates_passed=True)

    result = register_and_promote_candidate(
        _candidate(gates_passed=True),
        settings=_settings(),
        registry=registry,
    )

    assert result == PromotionResult(
        run_id="run-candidate",
        version="1",
        alias="champion",
        as_of_date=date(2026, 6, 1),
    )
    assert registry.alias_calls == [("petrocast-test", "champion", "1")]


def test_failed_gates_preserve_previous_champion() -> None:
    registry = FakeRegistry(gates_passed=False)
    previous = ModelVersion(
        name="petrocast-test",
        version="1",
        source="runs:/run-previous/model",
        run_id="run-previous",
        as_of_date=date(2026, 5, 1),
        metrics={"eval_model_mae_m3": 9.0},
        gates_passed=True,
    )
    registry.add_version(previous)
    registry.set_alias(name="petrocast-test", alias="champion", version="1")
    registry.alias_calls.clear()

    with pytest.raises(CandidateNotApprovedError):
        register_and_promote_candidate(
            _candidate(gates_passed=False),
            settings=_settings(),
            registry=registry,
        )

    assert registry.alias_calls == []
    assert registry.get_by_alias(name="petrocast-test", alias="champion") == previous


def test_retraining_assets_declare_transient_retry_policy() -> None:
    # ADR-0033: the three retraining assets do transient I/O (warehouse reads,
    # MLflow tracking/registry, artifact store) and must reuse the phase-two
    # RetryPolicy(max_retries=3, delay=30, EXPONENTIAL), same as the feature asset.
    for asset in (ml_training_candidate, ml_model_evaluation, ml_champion_promotion):
        assert asset.op.retry_policy == RETRAINING_RETRY_POLICY

    assert RETRAINING_RETRY_POLICY.max_retries == 3
    assert RETRAINING_RETRY_POLICY.delay == 30
    assert RETRAINING_RETRY_POLICY.backoff == dg.Backoff.EXPONENTIAL


def test_promotion_asset_blocks_and_preserves_champion_on_gate_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Materialize the real ml_champion_promotion asset (not just the helper) with
    # a gate-failed candidate: the registered candidate must be rejected as a
    # dg.Failure carrying promotion_status="blocked_by_quality_gates", and the
    # previously promoted champion alias must remain untouched (no set_alias).
    registry = FakeRegistry(gates_passed=False)
    previous = ModelVersion(
        name="petrocast-test",
        version="1",
        source="runs:/run-previous/model",
        run_id="run-previous",
        as_of_date=date(2026, 5, 1),
        metrics={"eval_model_mae_m3": 9.0},
        gates_passed=True,
    )
    registry.add_version(previous)
    registry.set_alias(name="petrocast-test", alias="champion", version="1")
    registry.alias_calls.clear()

    monkeypatch.setattr("petrocast_data.assets.training.get_settings", _settings)
    monkeypatch.setattr(
        "petrocast_data.assets.training.create_registry_client",
        lambda _settings: registry,
    )

    context = dg.build_asset_context(partition_key="2026-06-01")
    with pytest.raises(dg.Failure) as exc_info:
        ml_champion_promotion(context, _candidate(gates_passed=False))

    failure = exc_info.value
    assert failure.metadata["promotion_status"].value == "blocked_by_quality_gates"
    assert failure.metadata["mlflow_run_id"].value == "run-candidate"

    # The champion alias never moved: no set_alias call and version 1 still champion.
    assert registry.alias_calls == []
    assert registry.get_by_alias(name="petrocast-test", alias="champion") == previous
