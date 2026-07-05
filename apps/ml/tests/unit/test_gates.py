"""Gate verdicts and the report's JSON/MLflow projections."""

import json
from datetime import date
from typing import Any

import pytest

from petrocast_ml.evaluation.gates import (
    ARPS_MAPE_GATE,
    MASE_MEDIAN_GATE,
    NAIVE_MAE_GATE,
    GateResult,
    GateThresholds,
    evaluate_gates,
    gates_passed,
)
from petrocast_ml.evaluation.report import EvaluationReport


def _gates(**overrides: Any) -> tuple[GateResult, ...]:
    values: dict[str, Any] = {
        "mase_median": 0.8,
        "naive_mae_ratio": 0.9,
        "arps_mape_gap_pp": 1.0,
        "thresholds": GateThresholds(),
    }
    values.update(overrides)
    return evaluate_gates(**values)


def test_all_gates_pass() -> None:
    gates = _gates()
    assert [gate.passed for gate in gates] == [True, True, True]
    assert gates_passed(gates)


def test_mase_gate_blocks_at_threshold() -> None:
    gates = _gates(mase_median=1.0)  # strict <: 1.0 fails
    assert next(g for g in gates if g.name == MASE_MEDIAN_GATE).passed is False
    assert not gates_passed(gates)


def test_naive_gate_allows_equality_but_blocks_above() -> None:
    assert gates_passed(_gates(naive_mae_ratio=1.0))  # <=: matching naive passes
    gates = _gates(naive_mae_ratio=1.01)
    assert next(g for g in gates if g.name == NAIVE_MAE_GATE).passed is False
    assert not gates_passed(gates)


def test_arps_gate_never_blocks() -> None:
    gates = _gates(arps_mape_gap_pp=50.0)
    arps = next(g for g in gates if g.name == ARPS_MAPE_GATE)
    assert arps.passed is False and arps.blocking is False
    assert gates_passed(gates)


def test_arps_gate_not_evaluated_when_degraded() -> None:
    arps = next(g for g in _gates(arps_mape_gap_pp=None) if g.name == ARPS_MAPE_GATE)
    assert arps.passed is None and arps.value is None


def test_custom_thresholds_are_honored() -> None:
    hard = GateThresholds(mase_median_max=0.5)
    gates = _gates(mase_median=0.6, thresholds=hard)
    assert not gates_passed(gates)


def _report() -> EvaluationReport:
    return EvaluationReport(
        as_of_date=date(2026, 1, 1),
        horizons=(1, 2, 3),
        thresholds=GateThresholds(),
        wells_in_test=4,
        wells_eligible=3,
        wells_excluded_short_history=1,
        wells_mase_undefined=0,
        arps_fitted_wells=2,
        arps_failed_wells=1,
        arps_degraded=False,
        model_mae_m3=12.5,
        naive_mae_m3=14.0,
        distributions={"mase": {"p50": 0.7, "p75": 0.9, "p90": 1.1}},
        gates=_gates(),
        gates_passed=True,
    )


def test_report_round_trips_through_json() -> None:
    payload = json.loads(json.dumps(_report().to_dict()))
    assert payload["as_of_date"] == "2026-01-01"
    assert payload["gates_passed"] is True
    assert payload["distributions"]["mase"]["p90"] == pytest.approx(1.1)
    assert payload["gates"][0]["name"] == MASE_MEDIAN_GATE


def test_report_flattens_to_mlflow_metrics() -> None:
    metrics = _report().to_mlflow_metrics()
    assert metrics["eval_gates_passed"] == 1.0
    assert metrics["eval_mase_p50"] == pytest.approx(0.7)
    assert metrics["eval_model_mae_m3"] == pytest.approx(12.5)
    assert metrics["eval_gate_mase_median_passed"] == 1.0
    assert all(key.startswith("eval_") for key in metrics)


def test_report_skips_unevaluated_gate_metrics() -> None:
    report = _report()
    degraded = EvaluationReport(
        **{**report.to_kwargs(), "gates": _gates(arps_mape_gap_pp=None), "arps_degraded": True}
    )
    metrics = degraded.to_mlflow_metrics()
    assert "eval_gate_mape_vs_arps_passed" not in metrics
    assert "eval_gate_mape_vs_arps_value" not in metrics
