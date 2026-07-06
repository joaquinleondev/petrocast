"""MLflow model registry and reversible champion promotion (F3-16)."""

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Protocol, runtime_checkable

import mlflow
from mlflow import MlflowClient
from mlflow.entities.model_registry import ModelVersion as MlflowModelVersion
from mlflow.exceptions import MlflowException
from mlflow.protos.databricks_pb2 import RESOURCE_DOES_NOT_EXIST, ErrorCode

from petrocast_ml.config import MlSettings, get_settings
from petrocast_ml.tracking import AS_OF_DATE_TAG, GATES_PASSED_TAG, LOGGED_MODEL_URI_TAG

METRIC_TAG_PREFIX = "metric."
RUN_ID_TAG = "run_id"


class RegistryError(RuntimeError):
    """Base error for invalid or failed registry operations."""


class CandidateMetadataError(RegistryError):
    """Raised when a tracked candidate lacks promotion metadata."""


class CandidateNotApprovedError(RegistryError):
    """Raised when a candidate did not pass the blocking quality gates."""


@dataclass(frozen=True, slots=True)
class ModelVersion:
    """Registered candidate with the traceability needed for promotion."""

    name: str
    version: str
    source: str
    run_id: str
    as_of_date: date | None
    metrics: Mapping[str, float]
    gates_passed: bool | None


@runtime_checkable
class ModelRegistry(Protocol):
    """Port for registering, resolving and promoting model versions."""

    def register_candidate(
        self, *, name: str, run_id: str, source: str | None = None
    ) -> ModelVersion:
        """Register the model artifact and persist its run metadata."""
        ...

    def get_version(self, *, name: str, version: str) -> ModelVersion:
        """Resolve one registered version."""
        ...

    def get_by_alias(self, *, name: str, alias: str) -> ModelVersion:
        """Resolve a registered model version by alias."""
        ...

    def set_alias(self, *, name: str, alias: str, version: str) -> None:
        """Point an alias at an existing model version."""
        ...


def _parse_required_date(tags: Mapping[str, str]) -> date:
    raw_value = tags.get(AS_OF_DATE_TAG)
    if raw_value is None:
        raise CandidateMetadataError(f"run is missing required tag {AS_OF_DATE_TAG!r}")
    try:
        return date.fromisoformat(raw_value)
    except ValueError as error:
        raise CandidateMetadataError(
            f"run tag {AS_OF_DATE_TAG!r} is not an ISO date: {raw_value!r}"
        ) from error


def _parse_required_gate(tags: Mapping[str, str]) -> bool:
    raw_value = tags.get(GATES_PASSED_TAG)
    if raw_value == "true":
        return True
    if raw_value == "false":
        return False
    raise CandidateMetadataError(
        f"run tag {GATES_PASSED_TAG!r} must be 'true' or 'false', got {raw_value!r}"
    )


def _model_version_tags(
    *,
    run_id: str,
    as_of_date: date,
    metrics: Mapping[str, float],
    gates_passed: bool,
) -> dict[str, str]:
    tags = {
        RUN_ID_TAG: run_id,
        AS_OF_DATE_TAG: as_of_date.isoformat(),
        GATES_PASSED_TAG: str(gates_passed).lower(),
    }
    tags.update({f"{METRIC_TAG_PREFIX}{key}": str(value) for key, value in metrics.items()})
    return tags


def _normalize_version(version: MlflowModelVersion) -> ModelVersion:
    tags = version.tags or {}
    run_id = version.run_id or tags.get(RUN_ID_TAG)
    if run_id is None:
        raise CandidateMetadataError(
            f"registered model {version.name} version {version.version} has no run_id"
        )
    if version.source is None:
        raise CandidateMetadataError(
            f"registered model {version.name} version {version.version} has no source"
        )
    metrics: dict[str, float] = {}
    for key, value in tags.items():
        if key.startswith(METRIC_TAG_PREFIX):
            try:
                metrics[key.removeprefix(METRIC_TAG_PREFIX)] = float(value)
            except ValueError as error:
                raise CandidateMetadataError(
                    f"model version metric tag {key!r} is not numeric: {value!r}"
                ) from error
    return ModelVersion(
        name=version.name,
        version=str(version.version),
        source=version.source,
        run_id=run_id,
        as_of_date=_parse_required_date(tags),
        metrics=metrics,
        gates_passed=_parse_required_gate(tags),
    )


class MlflowModelRegistry:
    """``ModelRegistry`` backed by MLflow aliases and model-version tags."""

    def __init__(self, settings: MlSettings) -> None:
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        mlflow.set_registry_uri(settings.mlflow_tracking_uri)
        self._client = MlflowClient(
            tracking_uri=settings.mlflow_tracking_uri,
            registry_uri=settings.mlflow_tracking_uri,
        )

    def _ensure_registered_model(self, name: str) -> None:
        try:
            self._client.get_registered_model(name)
        except MlflowException as error:
            if error.error_code != ErrorCode.Name(RESOURCE_DOES_NOT_EXIST):
                raise
            self._client.create_registered_model(name)

    def register_candidate(
        self, *, name: str, run_id: str, source: str | None = None
    ) -> ModelVersion:
        run = self._client.get_run(run_id)
        as_of_date = _parse_required_date(run.data.tags)
        gates_passed = _parse_required_gate(run.data.tags)
        model_source = source or run.data.tags.get(LOGGED_MODEL_URI_TAG)
        if model_source is None:
            raise CandidateMetadataError(f"run is missing required tag {LOGGED_MODEL_URI_TAG!r}")
        metrics = {str(key): float(value) for key, value in run.data.metrics.items()}
        self._ensure_registered_model(name)
        for existing in self._client.search_model_versions(filter_string=f"name='{name}'"):
            if existing.run_id == run_id or (existing.tags or {}).get(RUN_ID_TAG) == run_id:
                return _normalize_version(existing)
        version = self._client.create_model_version(
            name=name,
            source=model_source,
            run_id=run_id,
            model_id=(
                model_source.removeprefix("models:/")
                if model_source.startswith("models:/m-")
                else None
            ),
            tags=_model_version_tags(
                run_id=run_id,
                as_of_date=as_of_date,
                metrics=metrics,
                gates_passed=gates_passed,
            ),
        )
        return _normalize_version(version)

    def get_version(self, *, name: str, version: str) -> ModelVersion:
        return _normalize_version(self._client.get_model_version(name, version))

    def get_by_alias(self, *, name: str, alias: str) -> ModelVersion:
        return _normalize_version(self._client.get_model_version_by_alias(name, alias))

    def set_alias(self, *, name: str, alias: str, version: str) -> None:
        self._client.set_registered_model_alias(name, alias, version)


def create_registry_client(settings: MlSettings | None = None) -> ModelRegistry:
    """Create the MLflow-backed registry client."""
    return MlflowModelRegistry(settings or get_settings())


def register_candidate(
    registry: ModelRegistry,
    *,
    run_id: str,
    settings: MlSettings | None = None,
    source: str | None = None,
) -> ModelVersion:
    """Register the tracked model and copy traceability metadata to its version."""
    resolved_settings = settings or get_settings()
    return registry.register_candidate(
        name=resolved_settings.mlflow_model_name,
        run_id=run_id,
        source=source,
    )


def promote_champion(
    registry: ModelRegistry,
    *,
    version: str,
    settings: MlSettings | None = None,
) -> ModelVersion:
    """Move the champion alias only when the candidate passed every blocking gate."""
    resolved_settings = settings or get_settings()
    candidate = registry.get_version(name=resolved_settings.mlflow_model_name, version=version)
    if candidate.as_of_date is None or not candidate.metrics or candidate.gates_passed is None:
        raise CandidateMetadataError(
            f"model {candidate.name} version {candidate.version} lacks promotion metadata"
        )
    if not candidate.gates_passed:
        raise CandidateNotApprovedError(
            f"model {candidate.name} version {candidate.version} did not pass quality gates"
        )
    registry.set_alias(
        name=resolved_settings.mlflow_model_name,
        alias=resolved_settings.mlflow_model_alias,
        version=candidate.version,
    )
    return registry.get_by_alias(
        name=resolved_settings.mlflow_model_name,
        alias=resolved_settings.mlflow_model_alias,
    )


def _version_payload(version: ModelVersion) -> dict[str, Any]:
    payload = asdict(version)
    payload["as_of_date"] = (
        version.as_of_date.isoformat() if version.as_of_date is not None else None
    )
    payload["metrics"] = dict(version.metrics)
    return payload


def _parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m petrocast_ml.registry",
        description="Register, inspect, promote or roll back the Petrocast champion model.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    register_parser = commands.add_parser("register")
    register_parser.add_argument("--run-id", required=True)
    register_parser.add_argument("--source")
    inspect_parser = commands.add_parser("inspect")
    inspect_parser.add_argument("--version")
    promote_parser = commands.add_parser("promote")
    promote_parser.add_argument("--version", required=True)
    rollback_parser = commands.add_parser("rollback")
    rollback_parser.add_argument("--to-version", required=True)
    return parser.parse_args(arguments)


def _run_cli(arguments: Sequence[str] | None = None) -> int:
    args = _parse_args(arguments)
    settings = get_settings()
    registry = create_registry_client(settings)
    try:
        if args.command == "register":
            version = register_candidate(
                registry,
                run_id=args.run_id,
                source=args.source,
                settings=settings,
            )
        elif args.command == "inspect":
            if args.version is not None:
                version = registry.get_version(
                    name=settings.mlflow_model_name,
                    version=args.version,
                )
            else:
                version = registry.get_by_alias(
                    name=settings.mlflow_model_name,
                    alias=settings.mlflow_model_alias,
                )
        elif args.command == "promote":
            version = promote_champion(registry, version=args.version, settings=settings)
        else:
            version = promote_champion(registry, version=args.to_version, settings=settings)
        print(json.dumps(_version_payload(version), sort_keys=True))
        return 0
    except (MlflowException, RegistryError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True))
        return 1


def main() -> None:
    raise SystemExit(_run_cli())


if __name__ == "__main__":
    main()


__all__ = [
    "CandidateMetadataError",
    "CandidateNotApprovedError",
    "MlflowModelRegistry",
    "ModelRegistry",
    "ModelVersion",
    "RegistryError",
    "create_registry_client",
    "promote_champion",
    "register_candidate",
]
