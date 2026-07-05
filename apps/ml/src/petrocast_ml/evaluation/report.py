"""Evaluation report: the single projection of a backtest (F3-15).

``EvaluationReport`` is what the training CLI persists next to the artifact
(``evaluation.json``), what tracking flattens into ``eval_*`` metrics on the
same MLflow run (ADR-0032) and what champion promotion (#16) reads to honor
the gates. Dataclass and projections only — no I/O here.
"""

from dataclasses import asdict, dataclass, fields
from datetime import date
from typing import Any, Final

from petrocast_ml.evaluation.gates import GateResult, GateThresholds

EVALUATION_FILE: Final = "evaluation.json"


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    as_of_date: date
    horizons: tuple[int, ...]
    thresholds: GateThresholds
    wells_in_test: int
    wells_eligible: int
    wells_excluded_short_history: int
    wells_mase_undefined: int
    arps_fitted_wells: int
    arps_failed_wells: int
    arps_degraded: bool
    model_mae_m3: float
    naive_mae_m3: float
    distributions: dict[str, dict[str, float]]
    gates: tuple[GateResult, ...]
    gates_passed: bool

    def to_kwargs(self) -> dict[str, Any]:
        """Shallow field dict (nested dataclasses intact) to build variants."""
        return {field.name: getattr(self, field.name) for field in fields(self)}

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe payload for ``evaluation.json`` and the CLI stdout."""
        payload = asdict(self)
        payload["as_of_date"] = self.as_of_date.isoformat()
        payload["horizons"] = list(self.horizons)
        payload["gates"] = [asdict(gate) for gate in self.gates]
        return payload

    def to_mlflow_metrics(self) -> dict[str, float]:
        """Flat ``eval_*`` metrics; unevaluated gate entries are omitted."""
        metrics: dict[str, float] = {
            "eval_model_mae_m3": self.model_mae_m3,
            "eval_naive_mae_m3": self.naive_mae_m3,
            "eval_wells_in_test": float(self.wells_in_test),
            "eval_wells_eligible": float(self.wells_eligible),
            "eval_wells_excluded_short_history": float(self.wells_excluded_short_history),
            "eval_wells_mase_undefined": float(self.wells_mase_undefined),
            "eval_arps_fitted_wells": float(self.arps_fitted_wells),
            "eval_arps_failed_wells": float(self.arps_failed_wells),
            "eval_arps_degraded": float(self.arps_degraded),
            "eval_gates_passed": float(self.gates_passed),
        }
        for metric_name, quantiles in self.distributions.items():
            for quantile_name, value in quantiles.items():
                metrics[f"eval_{metric_name}_{quantile_name}"] = value
        for gate in self.gates:
            if gate.passed is not None:
                metrics[f"eval_gate_{gate.name}_passed"] = float(gate.passed)
            if gate.value is not None:
                metrics[f"eval_gate_{gate.name}_value"] = gate.value
        return metrics


__all__ = ["EVALUATION_FILE", "EvaluationReport"]
