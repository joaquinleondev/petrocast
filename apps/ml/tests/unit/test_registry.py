"""Registry and champion-promotion contract for F3-16."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date

import pytest

from petrocast_ml import MlSettings
from petrocast_ml.registry import (
    CandidateMetadataError,
    CandidateNotApprovedError,
    ModelRegistry,
    ModelVersion,
    promote_champion,
    register_candidate,
)


@dataclass(frozen=True, slots=True)
class RunRecord:
    as_of_date: date | None
    metrics: Mapping[str, float]
    gates_passed: bool | None
    source: str


class FakeModelRegistry:
    """In-memory registry double with run metadata and movable aliases."""

    def __init__(self, runs: Mapping[str, RunRecord] | None = None) -> None:
        self.runs = dict(runs or {})
        self.versions: dict[tuple[str, str], ModelVersion] = {}
        self.aliases: dict[tuple[str, str], str] = {}

    def add_version(self, model_version: ModelVersion) -> None:
        self.versions[(model_version.name, model_version.version)] = model_version

    def register_candidate(
        self, *, name: str, run_id: str, source: str | None = None
    ) -> ModelVersion:
        record = self.runs[run_id]
        version = str(
            1
            + sum(registered_name == name for registered_name, _registered_version in self.versions)
        )
        candidate = ModelVersion(
            name=name,
            version=version,
            source=source or record.source,
            run_id=run_id,
            as_of_date=record.as_of_date,
            metrics=dict(record.metrics),
            gates_passed=record.gates_passed,
        )
        self.add_version(candidate)
        return candidate

    def get_version(self, *, name: str, version: str) -> ModelVersion:
        return self.versions[(name, version)]

    def get_by_alias(self, *, name: str, alias: str) -> ModelVersion:
        return self.get_version(name=name, version=self.aliases[(name, alias)])

    def set_alias(self, *, name: str, alias: str, version: str) -> None:
        self.get_version(name=name, version=version)
        self.aliases[(name, alias)] = version


def _settings() -> MlSettings:
    return MlSettings(
        mlflow_tracking_uri="sqlite:///unused.db",
        mlflow_model_name="petrocast-test",
        mlflow_model_alias="champion",
    )


def _approved_version(version: str, *, run_id: str | None = None) -> ModelVersion:
    return ModelVersion(
        name="petrocast-test",
        version=version,
        source=f"runs:/{run_id or f'run-{version}'}/model",
        run_id=run_id or f"run-{version}",
        as_of_date=date(2026, 1, 1),
        metrics={"eval_model_mae_m3": 8.5, "eval_naive_mae_m3": 10.0},
        gates_passed=True,
    )


def test_fake_registry_conforms_to_the_port() -> None:
    assert isinstance(FakeModelRegistry(), ModelRegistry)


def test_register_candidate_persists_traceability_and_gate_metadata() -> None:
    registry = FakeModelRegistry(
        {
            "run-accepted": RunRecord(
                as_of_date=date(2026, 1, 1),
                metrics={"eval_model_mae_m3": 8.5, "eval_naive_mae_m3": 10.0},
                gates_passed=True,
                source="runs:/run-accepted/model",
            )
        }
    )

    candidate = register_candidate(registry, run_id="run-accepted", settings=_settings())

    assert candidate == registry.get_version(name="petrocast-test", version="1")
    assert candidate.name == "petrocast-test"
    assert candidate.source == "runs:/run-accepted/model"
    assert candidate.run_id == "run-accepted"
    assert candidate.as_of_date == date(2026, 1, 1)
    assert candidate.metrics == {
        "eval_model_mae_m3": 8.5,
        "eval_naive_mae_m3": 10.0,
    }
    assert candidate.gates_passed is True


def test_register_candidate_forwards_an_explicit_source() -> None:
    registry = FakeModelRegistry(
        {
            "run-explicit": RunRecord(
                date(2025, 12, 1),
                {"eval_model_mae_m3": 9.0},
                True,
                "runs:/run-explicit/model",
            )
        }
    )

    candidate = register_candidate(
        registry,
        run_id="run-explicit",
        settings=_settings(),
        source="s3://petrocast-models/candidate",
    )

    assert candidate.source == "s3://petrocast-models/candidate"


def test_promote_champion_moves_alias_for_an_approved_candidate() -> None:
    registry = FakeModelRegistry()
    candidate = _approved_version("2")
    registry.add_version(candidate)

    promoted = promote_champion(registry, version="2", settings=_settings())

    assert promoted == candidate
    assert registry.get_by_alias(name="petrocast-test", alias="champion") == candidate


def test_promote_champion_rejects_failed_gate_without_moving_alias() -> None:
    registry = FakeModelRegistry()
    previous = _approved_version("1")
    rejected = replace(_approved_version("2"), gates_passed=False)
    registry.add_version(previous)
    registry.add_version(rejected)
    registry.set_alias(name="petrocast-test", alias="champion", version="1")

    with pytest.raises(CandidateNotApprovedError):
        promote_champion(registry, version="2", settings=_settings())

    assert registry.get_by_alias(name="petrocast-test", alias="champion") == previous


@pytest.mark.parametrize(
    ("field", "missing_value"),
    [
        ("as_of_date", None),
        ("metrics", {}),
        ("gates_passed", None),
    ],
)
def test_promote_champion_rejects_missing_metadata_without_moving_alias(
    field: str,
    missing_value: object,
) -> None:
    registry = FakeModelRegistry()
    previous = _approved_version("1")
    incomplete = replace(_approved_version("2"), **{field: missing_value})
    registry.add_version(previous)
    registry.add_version(incomplete)
    registry.set_alias(name="petrocast-test", alias="champion", version="1")

    with pytest.raises(CandidateMetadataError):
        promote_champion(registry, version="2", settings=_settings())

    assert registry.get_by_alias(name="petrocast-test", alias="champion") == previous


def test_rollback_repromotes_the_previous_approved_version() -> None:
    registry = FakeModelRegistry()
    first = _approved_version("1")
    second = _approved_version("2")
    registry.add_version(first)
    registry.add_version(second)

    promote_champion(registry, version="1", settings=_settings())
    promote_champion(registry, version="2", settings=_settings())
    rolled_back = promote_champion(registry, version="1", settings=_settings())

    assert rolled_back == first
    assert registry.get_by_alias(name="petrocast-test", alias="champion") == first
