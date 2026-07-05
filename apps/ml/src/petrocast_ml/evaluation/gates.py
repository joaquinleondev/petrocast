"""Promotion gates over the backtesting metrics (F3-15, ADR-0030).

Encodes the three contract-F gates: median per-well MASE (< 1.0, blocking),
aggregate MAE against the persistence naive (ratio ≤ 1.0, blocking — the PRD
"beat the naive" KPI) and the model-vs-Arps MAPE margin (informational, never
blocks: the fallback the issue reserves for a fiddly Arps). Thresholds are
injectable so hardening them is a config change, not an ADR re-opening.
"""

from dataclasses import dataclass
from typing import Final

MASE_MEDIAN_GATE: Final = "mase_median"
NAIVE_MAE_GATE: Final = "mae_vs_naive"
ARPS_MAPE_GATE: Final = "mape_vs_arps"


@dataclass(frozen=True, slots=True)
class GateThresholds:
    """ADR-0030 defaults; tighten via constructor, never by editing the ADR."""

    mase_median_max: float = 1.0
    naive_mae_ratio_max: float = 1.0
    arps_mape_margin_pp: float = 2.0


@dataclass(frozen=True, slots=True)
class GateResult:
    """One gate verdict; ``passed=None`` means not evaluable (degraded Arps)."""

    name: str
    value: float | None
    threshold: float
    passed: bool | None
    blocking: bool


def evaluate_gates(
    *,
    mase_median: float,
    naive_mae_ratio: float,
    arps_mape_gap_pp: float | None,
    thresholds: GateThresholds,
) -> tuple[GateResult, ...]:
    """Contract-F verdicts; the Arps gap is None when degraded or undefined."""
    return (
        GateResult(
            name=MASE_MEDIAN_GATE,
            value=mase_median,
            threshold=thresholds.mase_median_max,
            passed=mase_median < thresholds.mase_median_max,
            blocking=True,
        ),
        GateResult(
            name=NAIVE_MAE_GATE,
            value=naive_mae_ratio,
            threshold=thresholds.naive_mae_ratio_max,
            passed=naive_mae_ratio <= thresholds.naive_mae_ratio_max,
            blocking=True,
        ),
        GateResult(
            name=ARPS_MAPE_GATE,
            value=arps_mape_gap_pp,
            threshold=thresholds.arps_mape_margin_pp,
            passed=None
            if arps_mape_gap_pp is None
            else arps_mape_gap_pp <= thresholds.arps_mape_margin_pp,
            blocking=False,
        ),
    )


def gates_passed(gates: tuple[GateResult, ...]) -> bool:
    """A candidate is promotable when every blocking gate passes."""
    return all(gate.passed for gate in gates if gate.blocking)


__all__ = [
    "ARPS_MAPE_GATE",
    "MASE_MEDIAN_GATE",
    "NAIVE_MAE_GATE",
    "GateResult",
    "GateThresholds",
    "evaluate_gates",
    "gates_passed",
]
