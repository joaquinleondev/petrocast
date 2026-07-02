from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from petrocast_ml.config import MlSettings


@dataclass(frozen=True, slots=True)
class ModelVersion:
    name: str
    version: str
    source: str
    run_id: str | None = None


@runtime_checkable
class ModelRegistry(Protocol):
    """Port for resolving and promoting registered model versions."""

    def get_by_alias(self, *, name: str, alias: str) -> ModelVersion:
        """Resolve a registered model version by alias."""
        ...

    def set_alias(self, *, name: str, alias: str, version: str) -> None:
        """Point an alias at an existing model version."""
        ...


def create_registry_client(settings: MlSettings | None = None) -> ModelRegistry:
    """Create the MLflow-backed registry client."""
    del settings
    raise NotImplementedError("Registry integration is implemented by F3-16")


def promote_champion(
    registry: ModelRegistry,
    *,
    version: str,
    settings: MlSettings | None = None,
) -> ModelVersion:
    """Promote one registered version to the configured champion alias."""
    del registry, version, settings
    raise NotImplementedError("Champion promotion is implemented by F3-16")


__all__ = [
    "ModelRegistry",
    "ModelVersion",
    "create_registry_client",
    "promote_champion",
]
