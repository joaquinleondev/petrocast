from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from petrocast_ml.config import MlSettings

TrackingValue = str | int | float | bool


@dataclass(frozen=True, slots=True)
class RunMetadata:
    as_of_date: date
    features_version: str
    git_commit: str


@runtime_checkable
class TrackingClient(Protocol):
    """Port for recording reproducible training runs."""

    def log_parameters(self, parameters: Mapping[str, TrackingValue]) -> None:
        """Record immutable run parameters."""
        ...

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        """Record evaluation metrics."""
        ...

    def set_tags(self, tags: Mapping[str, str]) -> None:
        """Record traceability tags for the run."""
        ...


def create_tracking_client(settings: MlSettings | None = None) -> TrackingClient:
    """Create the MLflow-backed tracking client."""
    del settings
    raise NotImplementedError("Tracking integration is implemented by F3-14")


__all__ = ["RunMetadata", "TrackingClient", "TrackingValue", "create_tracking_client"]
