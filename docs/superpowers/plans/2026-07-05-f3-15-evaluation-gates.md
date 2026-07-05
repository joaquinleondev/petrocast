# F3-15 Evaluación, backtesting y gates — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evaluación post-training con métricas del contrato F (MASE/MAE/RMSE/MAPE-no-cero en distribución), doble baseline (naive + Arps best-effort) y gates automáticos que cortan el pipeline con exit 1, todo registrado en MLflow.

**Architecture:** Paquete puro `petrocast_ml/evaluation/` (metrics, arps, gates, report, orquestador `evaluate()`); `train()` intacto; `training/__main__.py` orquesta I/O (JSON en artifact, tracking, exit code). Spec: `docs/superpowers/specs/2026-07-05-f3-15-evaluation-gates-design.md`.

**Tech Stack:** pandas/numpy, scipy (`curve_fit`), LightGBM existente, MLflow vía puerto `TrackingClient` existente, pytest.

## Global Constraints

- Python 3.12, `mypy --strict` (override `ignore_missing_imports` solo para `scipy.*`), `ruff` con reglas del pyproject existente, línea 100.
- Contrato F (ADR-0030): elegibilidad ≥ 12 meses observados antes del cutoff; MASE denominador = promedio |Y_t − Y_{t−1}| sobre filas observadas sucesivas pre-cutoff (convención del fixture `expected_naive_backtest.csv`, columna `naive_insample_mae_m3`); gates: mediana MASE < 1.0 (bloqueante), MAE agregado modelo ≤ naive (bloqueante), Arps informativo (margen +2 pp, jamás bloquea).
- MAPE-no-cero se expresa en **porcentaje** (`*_pct`).
- Arps nunca lanza excepción hacia afuera; < 50 % de fits exitosos ⇒ `arps_degraded` y gate 3 `not evaluated`.
- Commits estilo repo: `feat(ml): ... [F3-15]` / `test(ml): ...`.
- Comandos desde `apps/ml/`: `.venv/bin/python -m pytest tests/... -v`, `.venv/bin/ruff check src tests`, `.venv/bin/mypy`.

---

### Task 1: Dependencia scipy + override mypy

**Files:**

- Modify: `apps/ml/pyproject.toml`

**Interfaces:**

- Produces: `scipy.optimize.curve_fit` importable; mypy no exige stubs de scipy.

- [ ] **Step 1: Agregar dependencia y override**

En `[project].dependencies` (orden alfabético):

```toml
    "scipy>=1.13,<2.0",
```

Al final de los overrides mypy:

```toml
# scipy ships partial type annotations; curve_fit and friends stay untyped.
[[tool.mypy.overrides]]
module = ["scipy", "scipy.*"]
ignore_missing_imports = true
```

- [ ] **Step 2: Sync y verificar import**

Run: `cd apps/ml && uv sync && .venv/bin/python -c "from scipy.optimize import curve_fit; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add apps/ml/pyproject.toml apps/ml/uv.lock
git commit -m "build(ml): add scipy dependency for Arps fitting [F3-15]"
```

---

### Task 2: `evaluation/metrics.py`

**Files:**

- Create: `apps/ml/src/petrocast_ml/evaluation/__init__.py` (temporal, vacío con docstring; el orquestador llega en Task 6)
- Create: `apps/ml/src/petrocast_ml/evaluation/metrics.py`
- Test: `apps/ml/tests/unit/test_evaluation_metrics.py`

**Interfaces:**

- Consumes: `NAIVE_COLUMN`, `TARGET_COLUMN` de `petrocast_ml.training.dataset`; fixtures `production_monthly`, `expected_naive_backtest` del conftest.
- Produces: `PREDICTION_COLUMN: str`, `MIN_HISTORY_MONTHS: int`, `eligible_wells(production, *, as_of_date) -> list[str]`, `one_step_naive_mae(production, *, as_of_date) -> pd.Series` (index well_id), `per_well_metrics(test, *, insample_naive_mae) -> pd.DataFrame` (index well_id; columnas `model_mae_m3`, `model_rmse_m3`, `naive_mae_m3`, `mape_nonzero_pct`, `mase`; NaN = indefinido), `distribution(values) -> dict[str, float]` (`p50/p75/p90`, `{}` si vacío).

- [ ] **Step 1: Failing tests**

```python
"""Metric semantics of contract F against hand-computed and frozen values."""

import numpy as np
import pandas as pd
import pytest

from petrocast_ml.evaluation.metrics import (
    PREDICTION_COLUMN,
    distribution,
    eligible_wells,
    one_step_naive_mae,
    per_well_metrics,
)
from petrocast_ml.training.dataset import NAIVE_COLUMN, TARGET_COLUMN

CUTOFF = pd.Timestamp("2026-01-01")


def test_eligibility_excludes_wells_under_12_observed_months(
    production_monthly: pd.DataFrame,
) -> None:
    # 70003 is the cold-start well: 5 observed months before the cutoff.
    assert eligible_wells(production_monthly, as_of_date=CUTOFF) == ["70001", "70002", "70004"]


def test_insample_naive_mae_matches_frozen_fixture(
    production_monthly: pd.DataFrame, expected_naive_backtest: pd.DataFrame
) -> None:
    # The F3-10 fixture froze the MASE denominator convention: successive
    # observed rows, calendar gaps collapse (70002 is the well with gaps).
    computed = one_step_naive_mae(production_monthly, as_of_date=CUTOFF)
    expected = expected_naive_backtest.groupby("well_id")["naive_insample_mae_m3"].first()
    for well_id, value in expected.items():
        assert computed[well_id] == pytest.approx(value), well_id


def test_insample_naive_mae_needs_two_observations() -> None:
    production = pd.DataFrame(
        {
            "well_id": ["w1"],
            "production_month": [pd.Timestamp("2025-12-01")],
            "oil_prod_m3": [100.0],
        }
    )
    assert "w1" not in one_step_naive_mae(production, as_of_date=CUTOFF).index


def _test_frame() -> pd.DataFrame:
    # One well, three pooled horizons: errors 1, 2, 3 -> MAE 2; naive errors 2, 2, 2.
    return pd.DataFrame(
        {
            "well_id": ["w1", "w1", "w1"],
            TARGET_COLUMN: [10.0, 20.0, 0.0],
            PREDICTION_COLUMN: [11.0, 18.0, 3.0],
            NAIVE_COLUMN: [12.0, 22.0, 2.0],
        }
    )


def test_per_well_metrics_hand_computed() -> None:
    metrics = per_well_metrics(_test_frame(), insample_naive_mae=pd.Series({"w1": 4.0}))
    row = metrics.loc["w1"]
    assert row["model_mae_m3"] == pytest.approx(2.0)
    assert row["model_rmse_m3"] == pytest.approx(np.sqrt((1 + 4 + 9) / 3))
    assert row["naive_mae_m3"] == pytest.approx(2.0)
    assert row["mase"] == pytest.approx(2.0 / 4.0)
    # MAPE skips the zero-actual row: mean(1/10, 2/20) * 100.
    assert row["mape_nonzero_pct"] == pytest.approx(10.0)


def test_mase_undefined_when_denominator_is_zero_or_missing() -> None:
    frame = _test_frame()
    flat = per_well_metrics(frame, insample_naive_mae=pd.Series({"w1": 0.0}))
    missing = per_well_metrics(frame, insample_naive_mae=pd.Series(dtype=float))
    assert np.isnan(flat.loc["w1", "mase"])
    assert np.isnan(missing.loc["w1", "mase"])


def test_mape_undefined_for_all_zero_actuals() -> None:
    frame = _test_frame()
    frame[TARGET_COLUMN] = 0.0
    metrics = per_well_metrics(frame, insample_naive_mae=pd.Series({"w1": 4.0}))
    assert np.isnan(metrics.loc["w1", "mape_nonzero_pct"])


def test_per_well_metrics_skips_rows_without_naive() -> None:
    frame = _test_frame()
    frame.loc[2, NAIVE_COLUMN] = np.nan
    metrics = per_well_metrics(frame, insample_naive_mae=pd.Series({"w1": 4.0}))
    assert metrics.loc["w1", "model_mae_m3"] == pytest.approx(1.5)


def test_distribution_quantiles_and_empty() -> None:
    values = pd.Series([1.0, 2.0, 3.0, 4.0])
    result = distribution(values)
    assert result == {
        "p50": pytest.approx(2.5),
        "p75": pytest.approx(3.25),
        "p90": pytest.approx(3.7),
    }
    assert distribution(pd.Series(dtype=float)) == {}
    assert distribution(pd.Series([np.nan])) == {}
```

- [ ] **Step 2: Run para ver el fail**

Run: `cd apps/ml && .venv/bin/python -m pytest tests/unit/test_evaluation_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'petrocast_ml.evaluation'`

- [ ] **Step 3: Implementación**

`evaluation/__init__.py` (placeholder de Task 2; Task 6 lo reemplaza):

```python
"""Backtesting evaluation and quality gates (F3-15)."""
```

`evaluation/metrics.py`:

```python
"""Per-well backtesting metrics (F3-15, contract F).

Implements the metric semantics frozen in ADR-0030 over the single-origin
test split: MAE/RMSE in m³ pooled over horizons, MASE against the in-sample
one-step naive (successive observed rows — the convention frozen by the F3-10
fixture ``expected_naive_backtest.csv``), MAPE restricted to non-zero actuals
(in percent, the PRD vocabulary) and the p50/p75/p90 distribution view that
gates and report consume. Pure pandas/numpy — no I/O, no MLflow.
"""

from typing import Final

import numpy as np
import pandas as pd

from petrocast_ml.training.dataset import NAIVE_COLUMN, TARGET_COLUMN

PREDICTION_COLUMN: Final = "prediction_m3"

#: ADR-0030 eligibility filter: wells need this many observed months before
#: the cutoff to enter metrics and gates (no reliable Arps or seasonality below).
MIN_HISTORY_MONTHS: Final = 12

_QUANTILES: Final[dict[str, float]] = {"p50": 0.5, "p75": 0.75, "p90": 0.9}


def _observed_before(production: pd.DataFrame, as_of_date: pd.Timestamp) -> pd.DataFrame:
    return production.loc[
        (production["production_month"] < as_of_date) & production["oil_prod_m3"].notna()
    ]


def eligible_wells(production: pd.DataFrame, *, as_of_date: pd.Timestamp) -> list[str]:
    """Wells with >= MIN_HISTORY_MONTHS observed months strictly before the cutoff."""
    observed = _observed_before(production, as_of_date)
    counts = observed.groupby("well_id")["production_month"].nunique()
    return sorted(str(well_id) for well_id in counts.index[counts >= MIN_HISTORY_MONTHS])


def one_step_naive_mae(production: pd.DataFrame, *, as_of_date: pd.Timestamp) -> pd.Series:
    """MASE denominator per well: mean |Y_t − Y_{t−1}| over successive observed rows.

    Successive means successive observed months in chronological order —
    calendar gaps collapse (fixture-frozen convention). Wells with fewer than
    two observations produce no entry.
    """
    observed = _observed_before(production, as_of_date).sort_values(
        ["well_id", "production_month"]
    )
    diffs = observed.groupby("well_id")["oil_prod_m3"].diff().abs()
    return diffs.groupby(observed["well_id"]).mean().dropna()


def per_well_metrics(test: pd.DataFrame, *, insample_naive_mae: pd.Series) -> pd.DataFrame:
    """One metrics row per well over its evaluable test rows, pooled horizons.

    NaN encodes "undefined": MASE when the denominator is missing or zero,
    MAPE when the well has no positive actuals in the window.
    """
    evaluable = test.loc[test[NAIVE_COLUMN].notna()]
    index: list[str] = []
    rows: list[dict[str, float]] = []
    for well_id, group in evaluable.groupby("well_id"):
        model_abs = (group[TARGET_COLUMN] - group[PREDICTION_COLUMN]).abs()
        naive_abs = (group[TARGET_COLUMN] - group[NAIVE_COLUMN]).abs()
        positive = group.loc[group[TARGET_COLUMN] > 0]
        mape = (
            float(
                ((positive[TARGET_COLUMN] - positive[PREDICTION_COLUMN]).abs()
                 / positive[TARGET_COLUMN]).mean() * 100.0
            )
            if len(positive)
            else float("nan")
        )
        index.append(str(well_id))
        rows.append(
            {
                "model_mae_m3": float(model_abs.mean()),
                "model_rmse_m3": float(np.sqrt((model_abs**2).mean())),
                "naive_mae_m3": float(naive_abs.mean()),
                "mape_nonzero_pct": mape,
            }
        )
    metrics = pd.DataFrame(rows, index=pd.Index(index, name="well_id"))
    denominator = insample_naive_mae.reindex(metrics.index)
    metrics["mase"] = metrics["model_mae_m3"] / denominator.where(denominator > 0)
    return metrics


def distribution(values: pd.Series) -> dict[str, float]:
    """p50/p75/p90 over wells where the metric is defined; empty dict if none."""
    defined = values.dropna()
    if defined.empty:
        return {}
    return {name: float(defined.quantile(q)) for name, q in _QUANTILES.items()}


__all__ = [
    "MIN_HISTORY_MONTHS",
    "PREDICTION_COLUMN",
    "distribution",
    "eligible_wells",
    "one_step_naive_mae",
    "per_well_metrics",
]
```

- [ ] **Step 4: Run para ver el pass**

Run: `cd apps/ml && .venv/bin/python -m pytest tests/unit/test_evaluation_metrics.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/ml/src/petrocast_ml/evaluation tests
git commit -m "feat(ml): per-well backtesting metrics with MASE and eligibility [F3-15]"
```

---

### Task 3: `evaluation/arps.py`

**Files:**

- Create: `apps/ml/src/petrocast_ml/evaluation/arps.py`
- Test: `apps/ml/tests/unit/test_arps.py`

**Interfaces:**

- Produces: `MIN_POSITIVE_POINTS: int = 6`, `ArpsFit(qi, di, b, t0_month)` (frozen dataclass), `fit_well(production_train) -> ArpsFit | None`, `forecast(fit, target_months) -> NDArray[np.float64]`.

- [ ] **Step 1: Failing tests**

```python
"""Best-effort Arps fitting: recovers synthetic declines, degrades to None."""

import numpy as np
import pandas as pd
import pytest

from petrocast_ml.evaluation.arps import MIN_POSITIVE_POINTS, ArpsFit, fit_well, forecast


def _series(rates: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    months = pd.date_range(start, periods=len(rates), freq="MS")
    return pd.DataFrame(
        {"well_id": "w1", "production_month": months, "oil_prod_m3": rates}
    )


def test_recovers_exponential_decline() -> None:
    # Exponential is the b -> 0 edge of the hyperbolic family.
    t = np.arange(24, dtype=float)
    rates = 500.0 * np.exp(-0.08 * t)
    fit = fit_well(_series(list(rates)))
    assert fit is not None
    future = pd.Series(pd.date_range("2026-01-01", periods=3, freq="MS"))
    expected = 500.0 * np.exp(-0.08 * np.array([24.0, 25.0, 26.0]))
    assert forecast(fit, future) == pytest.approx(expected, rel=0.05)


def test_recovers_hyperbolic_decline() -> None:
    t = np.arange(30, dtype=float)
    rates = 800.0 / np.power(1.0 + 0.6 * 0.09 * t, 1.0 / 0.6)
    fit = fit_well(_series(list(rates), start="2023-07-01"))
    assert fit is not None
    assert fit.b == pytest.approx(0.6, abs=0.15)
    future = pd.Series(pd.date_range("2026-01-01", periods=3, freq="MS"))
    expected = 800.0 / np.power(1.0 + 0.6 * 0.09 * np.array([30.0, 31.0, 32.0]), 1.0 / 0.6)
    assert forecast(fit, future) == pytest.approx(expected, rel=0.05)


def test_zero_months_are_excluded_from_the_fit_but_not_the_clock() -> None:
    # A shut-in month keeps its calendar slot: t counts months since first
    # observation, so the decline clock does not compress around gaps.
    t = np.arange(24, dtype=float)
    rates = list(500.0 * np.exp(-0.08 * t))
    rates[10] = 0.0  # shut-in
    fit = fit_well(_series(rates))
    assert fit is not None
    future = pd.Series(pd.date_range("2026-01-01", periods=1, freq="MS"))
    assert forecast(fit, future) == pytest.approx([500.0 * np.exp(-0.08 * 24.0)], rel=0.08)


def test_too_few_positive_points_returns_none() -> None:
    rates = [0.0] * 10 + [100.0] * (MIN_POSITIVE_POINTS - 1)
    assert fit_well(_series(rates)) is None


def test_all_zero_or_empty_returns_none() -> None:
    assert fit_well(_series([0.0] * 12)) is None
    assert fit_well(_series([])) is None


def test_never_raises_on_unstructured_series() -> None:
    # Increasing production contradicts a decline; best-effort means None or a
    # (bad) fit, never an exception.
    rates = list(np.linspace(10.0, 900.0, 18))
    result = fit_well(_series(rates))
    assert result is None or isinstance(result, ArpsFit)
```

- [ ] **Step 2: Run para ver el fail**

Run: `cd apps/ml && .venv/bin/python -m pytest tests/unit/test_arps.py -v`
Expected: FAIL — `ModuleNotFoundError` (arps)

- [ ] **Step 3: Implementación**

```python
"""Best-effort Arps decline baseline (F3-15, ADR-0030 / P4).

Fits the hyperbolic Arps model ``q(t) = qi / (1 + b·Di·t)^(1/b)`` per well
with scipy's bounded least squares; ``b`` is floored at 1e-6 so the b → 0
exponential edge stays numerically defined. Shut-in zero months are excluded
from the fit (standard DCA: the decline describes producing rates) but keep
their calendar slot in ``t``. Every per-well failure — too few positive
points, no convergence, non-finite parameters — returns ``None`` so the
caller counts it: Arps never raises past this module and never blocks a gate.
"""

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.optimize import curve_fit

#: Minimum positive-production months required to attempt a fit.
MIN_POSITIVE_POINTS: Final = 6

_B_FLOOR: Final = 1e-6
_MAX_EVALUATIONS: Final = 5000


@dataclass(frozen=True, slots=True)
class ArpsFit:
    """Fitted decline; ``t`` is months elapsed since ``t0_month``."""

    qi: float
    di: float
    b: float
    t0_month: pd.Timestamp


def _hyperbolic(
    t: NDArray[np.float64], qi: float, di: float, b: float
) -> NDArray[np.float64]:
    return qi / np.power(1.0 + b * di * t, 1.0 / b)


def _months_since(months: pd.Series, origin: pd.Timestamp) -> NDArray[np.float64]:
    absolute = months.dt.year.to_numpy() * 12 + months.dt.month.to_numpy()
    return (absolute - (origin.year * 12 + origin.month)).astype(np.float64)


def fit_well(production_train: pd.DataFrame) -> ArpsFit | None:
    """Fit one well's pre-cutoff series; ``None`` whenever it is not fittable."""
    observed = production_train.loc[production_train["oil_prod_m3"].notna()]
    positive = observed.loc[observed["oil_prod_m3"] > 0]
    if len(positive) < MIN_POSITIVE_POINTS:
        return None

    t0 = pd.Timestamp(observed["production_month"].min())
    t = _months_since(positive["production_month"], t0)
    q = positive["oil_prod_m3"].to_numpy(dtype=np.float64)
    recent_peak = float(q[-12:].max())
    try:
        params, _ = curve_fit(
            _hyperbolic,
            t,
            q,
            p0=(recent_peak, 0.1, 0.5),
            bounds=((1e-9, 1e-9, _B_FLOOR), (np.inf, 10.0, 1.0)),
            maxfev=_MAX_EVALUATIONS,
        )
    except (RuntimeError, ValueError):
        return None
    qi, di, b = (float(value) for value in params)
    if not np.isfinite((qi, di, b)).all():
        return None
    return ArpsFit(qi=qi, di=di, b=b, t0_month=t0)


def forecast(fit: ArpsFit, target_months: pd.Series) -> NDArray[np.float64]:
    """Predicted monthly rate (m³/month) at each target month."""
    t = _months_since(target_months, fit.t0_month)
    return _hyperbolic(t, fit.qi, fit.di, fit.b)


__all__ = ["MIN_POSITIVE_POINTS", "ArpsFit", "fit_well", "forecast"]
```

- [ ] **Step 4: Run para ver el pass**

Run: `cd apps/ml && .venv/bin/python -m pytest tests/unit/test_arps.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/ml/src/petrocast_ml/evaluation/arps.py apps/ml/tests/unit/test_arps.py
git commit -m "feat(ml): best-effort Arps decline baseline via scipy [F3-15]"
```

---

### Task 4: `evaluation/gates.py` + `evaluation/report.py`

**Files:**

- Create: `apps/ml/src/petrocast_ml/evaluation/gates.py`
- Create: `apps/ml/src/petrocast_ml/evaluation/report.py`
- Test: `apps/ml/tests/unit/test_gates.py`

**Interfaces:**

- Produces (gates): `MASE_MEDIAN_GATE = "mase_median"`, `NAIVE_MAE_GATE = "mae_vs_naive"`, `ARPS_MAPE_GATE = "mape_vs_arps"`, `GateThresholds(mase_median_max=1.0, naive_mae_ratio_max=1.0, arps_mape_margin_pp=2.0)`, `GateResult(name, value: float | None, threshold, passed: bool | None, blocking)`, `evaluate_gates(*, mase_median, naive_mae_ratio, arps_mape_gap_pp, thresholds) -> tuple[GateResult, ...]`, `gates_passed(gates) -> bool`.
- Produces (report): `EVALUATION_FILE = "evaluation.json"`, `EvaluationReport` frozen dataclass con campos `as_of_date, horizons, thresholds, wells_in_test, wells_eligible, wells_excluded_short_history, wells_mase_undefined, arps_fitted_wells, arps_failed_wells, arps_degraded, model_mae_m3, naive_mae_m3, distributions, gates, gates_passed` y métodos `to_dict() -> dict[str, Any]` (JSON-safe) y `to_mlflow_metrics() -> dict[str, float]` (todo prefijo `eval_`).

- [ ] **Step 1: Failing tests**

```python
"""Gate verdicts and the report's JSON/MLflow projections."""

import json
from datetime import date

import pytest

from petrocast_ml.evaluation.gates import (
    ARPS_MAPE_GATE,
    MASE_MEDIAN_GATE,
    NAIVE_MAE_GATE,
    GateThresholds,
    evaluate_gates,
    gates_passed,
)
from petrocast_ml.evaluation.report import EvaluationReport


def _gates(**overrides: float | None) -> tuple:
    values: dict = {
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
```

Nota: `to_kwargs()` es un helper del report (dict de campos, sin proyección JSON) para reconstruir variantes en tests y en #16.

- [ ] **Step 2: Run para ver el fail**

Run: `cd apps/ml && .venv/bin/python -m pytest tests/unit/test_gates.py -v`
Expected: FAIL — `ModuleNotFoundError` (gates)

- [ ] **Step 3: Implementación**

`gates.py`:

```python
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
```

`report.py`:

```python
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
```

- [ ] **Step 4: Run para ver el pass**

Run: `cd apps/ml && .venv/bin/python -m pytest tests/unit/test_gates.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/ml/src/petrocast_ml/evaluation apps/ml/tests/unit/test_gates.py
git commit -m "feat(ml): promotion gates and evaluation report projections [F3-15]"
```

---

### Task 5: Orquestador `evaluate()`

**Files:**

- Modify: `apps/ml/src/petrocast_ml/evaluation/__init__.py` (reemplaza placeholder)
- Test: `apps/ml/tests/unit/test_evaluation.py`

**Interfaces:**

- Consumes: todo lo de Tasks 2–4; `temporal_split`, `prepare_model_input`, `TrainableModel`, `TrainingRequest`.
- Produces: `evaluate(model, dataset, production, *, request, thresholds=None) -> EvaluationReport`; constante `ARPS_MIN_FITTED_SHARE = 0.5`; re-exporta `EvaluationReport, GateThresholds, GateResult, EVALUATION_FILE, evaluate`.

- [ ] **Step 1: Failing tests**

```python
"""End-to-end evaluate(): gates pass/fail with stub models on the fixtures."""

import json
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import pytest
from numpy.typing import NDArray

from petrocast_ml.evaluation import EvaluationReport, evaluate
from petrocast_ml.training import TARGET_COLUMN, TrainingRequest, build_training_dataset


@dataclass
class StubModel:
    """Returns preset predictions positionally; evaluate() must not re-order."""

    predictions: NDArray[np.float64]

    def fit(self, features: pd.DataFrame, target: pd.Series) -> "StubModel":
        return self

    def predict(self, features: pd.DataFrame) -> NDArray[np.float64]:
        assert len(features) == len(self.predictions)
        return self.predictions


@pytest.fixture
def dataset(production_monthly: pd.DataFrame, well_features: pd.DataFrame) -> pd.DataFrame:
    return build_training_dataset(well_features, production_monthly, horizons=(1, 2, 3))


@pytest.fixture
def request_eval() -> TrainingRequest:
    return TrainingRequest(as_of_date=date(2026, 1, 1), features_version="fixtures", horizon=3)


def _test_targets(dataset: pd.DataFrame) -> NDArray[np.float64]:
    test = dataset.loc[dataset["as_of_date"] == pd.Timestamp("2026-01-01")]
    return test[TARGET_COLUMN].to_numpy(dtype=np.float64)


def test_perfect_model_passes_gates(
    dataset: pd.DataFrame, production_monthly: pd.DataFrame, request_eval: TrainingRequest
) -> None:
    report = evaluate(
        StubModel(_test_targets(dataset)), dataset, production_monthly, request=request_eval
    )
    assert report.gates_passed
    assert report.wells_in_test == 4
    assert report.wells_eligible == 3  # 70003 filtered: 5 observed months < 12
    assert report.wells_excluded_short_history == 1
    assert report.model_mae_m3 == pytest.approx(0.0)
    assert report.arps_fitted_wells + report.arps_failed_wells == 3
    assert json.loads(json.dumps(report.to_dict()))  # JSON-safe end to end


def test_terrible_model_fails_both_blocking_gates(
    dataset: pd.DataFrame, production_monthly: pd.DataFrame, request_eval: TrainingRequest
) -> None:
    report = evaluate(
        StubModel(_test_targets(dataset) + 10_000.0),
        dataset,
        production_monthly,
        request=request_eval,
    )
    assert not report.gates_passed
    blocking = [gate for gate in report.gates if gate.blocking]
    assert all(gate.passed is False for gate in blocking)


def test_no_eligible_wells_raises(
    dataset: pd.DataFrame, production_monthly: pd.DataFrame, request_eval: TrainingRequest
) -> None:
    # Truncate history to 3 months per well: nobody reaches 12 observed months.
    truncated = (
        production_monthly.sort_values("production_month")
        .groupby("well_id")
        .tail(3)
        .reset_index(drop=True)
    )
    test_rows = int((dataset["as_of_date"] == pd.Timestamp("2026-01-01")).sum())
    with pytest.raises(ValueError, match="eligible"):
        evaluate(
            StubModel(np.zeros(test_rows)), dataset, truncated, request=request_eval
        )


def test_report_distributions_cover_contract_metrics(
    dataset: pd.DataFrame, production_monthly: pd.DataFrame, request_eval: TrainingRequest
) -> None:
    report = evaluate(
        StubModel(_test_targets(dataset)), dataset, production_monthly, request=request_eval
    )
    assert {"mase", "model_mae_m3", "naive_mae_m3"} <= set(report.distributions)
    for quantiles in report.distributions.values():
        assert set(quantiles) == {"p50", "p75", "p90"}


def test_returns_evaluation_report_type(
    dataset: pd.DataFrame, production_monthly: pd.DataFrame, request_eval: TrainingRequest
) -> None:
    report = evaluate(
        StubModel(_test_targets(dataset)), dataset, production_monthly, request=request_eval
    )
    assert isinstance(report, EvaluationReport)
```

- [ ] **Step 2: Run para ver el fail**

Run: `cd apps/ml && .venv/bin/python -m pytest tests/unit/test_evaluation.py -v`
Expected: FAIL — `ImportError: cannot import name 'evaluate'`

- [ ] **Step 3: Implementación** (reemplaza `evaluation/__init__.py`)

```python
"""Backtesting evaluation and quality gates (F3-15).

``evaluate`` is the pure orchestrator: it reproduces the single-origin test
split (contract F), applies the eligibility filter, computes the per-well
metric distributions, fits the best-effort Arps baseline and returns the
``EvaluationReport`` with the gate verdicts. The training CLI is the only
caller wrapping it with I/O (artifact JSON, MLflow, exit code).
"""

import numpy as np
import pandas as pd

from petrocast_ml.evaluation.arps import fit_well, forecast
from petrocast_ml.evaluation.gates import (
    GateResult,
    GateThresholds,
    evaluate_gates,
    gates_passed,
)
from petrocast_ml.evaluation.metrics import (
    MIN_HISTORY_MONTHS,
    PREDICTION_COLUMN,
    distribution,
    eligible_wells,
    one_step_naive_mae,
    per_well_metrics,
)
from petrocast_ml.evaluation.report import EVALUATION_FILE, EvaluationReport
from petrocast_ml.training.contracts import TrainableModel, TrainingRequest
from petrocast_ml.training.dataset import (
    HORIZON_COLUMN,
    NAIVE_COLUMN,
    TARGET_COLUMN,
    temporal_split,
)
from petrocast_ml.training.model import prepare_model_input

#: Below this share of successful fits the Arps comparison degrades to "not
#: evaluated" (issue fallback) instead of pretending a partial baseline.
ARPS_MIN_FITTED_SHARE = 0.5


def evaluate(
    model: TrainableModel,
    dataset: pd.DataFrame,
    production: pd.DataFrame,
    *,
    request: TrainingRequest,
    thresholds: GateThresholds | None = None,
) -> EvaluationReport:
    """Backtest ``model`` on the request's single-origin test split (contract F).

    Raises:
        ValueError: when no eligible well is evaluable, or MASE is undefined
            for every eligible well — an evaluation without a verdict must
            fail loudly, never pass silently.
    """
    thresholds = thresholds or GateThresholds()
    cutoff = pd.Timestamp(request.as_of_date)

    test = temporal_split(dataset, request=request).test.copy()
    test[PREDICTION_COLUMN] = np.asarray(
        model.predict(prepare_model_input(test)), dtype=float
    )

    wells_in_test = int(test["well_id"].nunique())
    eligible = eligible_wells(production, as_of_date=cutoff)
    evaluable = test.loc[test["well_id"].isin(eligible) & test[NAIVE_COLUMN].notna()]
    if evaluable.empty:
        raise ValueError(
            f"no eligible wells (>= {MIN_HISTORY_MONTHS} observed months before "
            f"{request.as_of_date}) with an evaluable naive baseline in the test split"
        )

    per_well = per_well_metrics(
        evaluable, insample_naive_mae=one_step_naive_mae(production, as_of_date=cutoff)
    )
    mase = per_well["mase"].dropna()
    if mase.empty:
        raise ValueError("MASE undefined for every eligible well (flat pre-cutoff series)")

    arps_mape, fitted, failed = _arps_mape_per_well(evaluable, production, cutoff=cutoff)
    attempted = fitted + failed
    arps_degraded = attempted == 0 or fitted / attempted < ARPS_MIN_FITTED_SHARE

    model_mae = float((evaluable[TARGET_COLUMN] - evaluable[PREDICTION_COLUMN]).abs().mean())
    naive_mae = float((evaluable[TARGET_COLUMN] - evaluable[NAIVE_COLUMN]).abs().mean())
    if naive_mae > 0:
        naive_ratio = model_mae / naive_mae
    else:  # perfect naive: only a perfect model matches it
        naive_ratio = 0.0 if model_mae == 0 else float("inf")

    arps_gap: float | None = None
    paired = per_well.loc[per_well.index.isin(arps_mape.index), "mape_nonzero_pct"].dropna()
    if not arps_degraded and not paired.empty:
        arps_gap = float(paired.median() - arps_mape.reindex(paired.index).median())

    gates = evaluate_gates(
        mase_median=float(mase.median()),
        naive_mae_ratio=naive_ratio,
        arps_mape_gap_pp=arps_gap,
        thresholds=thresholds,
    )

    distributions = {
        "mase": distribution(per_well["mase"]),
        "model_mae_m3": distribution(per_well["model_mae_m3"]),
        "naive_mae_m3": distribution(per_well["naive_mae_m3"]),
        "mape_nonzero_pct": distribution(per_well["mape_nonzero_pct"]),
        "arps_mape_nonzero_pct": distribution(arps_mape),
    }

    return EvaluationReport(
        as_of_date=request.as_of_date,
        horizons=tuple(sorted(int(h) for h in test[HORIZON_COLUMN].unique())),
        thresholds=thresholds,
        wells_in_test=wells_in_test,
        wells_eligible=int(evaluable["well_id"].nunique()),
        wells_excluded_short_history=wells_in_test
        - int(test.loc[test["well_id"].isin(eligible), "well_id"].nunique()),
        wells_mase_undefined=int(per_well["mase"].isna().sum()),
        arps_fitted_wells=fitted,
        arps_failed_wells=failed,
        arps_degraded=arps_degraded,
        model_mae_m3=model_mae,
        naive_mae_m3=naive_mae,
        distributions={name: values for name, values in distributions.items() if values},
        gates=gates,
        gates_passed=gates_passed(gates),
    )


def _arps_mape_per_well(
    evaluable: pd.DataFrame, production: pd.DataFrame, *, cutoff: pd.Timestamp
) -> tuple[pd.Series, int, int]:
    """Arps MAPE-no-cero per fitted well; counts of fitted and failed fits."""
    train_production = production.loc[production["production_month"] < cutoff]
    mapes: dict[str, float] = {}
    fitted = 0
    failed = 0
    for well_id, group in evaluable.groupby("well_id"):
        fit = fit_well(train_production.loc[train_production["well_id"] == well_id])
        if fit is None:
            failed += 1
            continue
        fitted += 1
        positive = group.loc[group[TARGET_COLUMN] > 0]
        if positive.empty:
            continue  # fit succeeded but MAPE is undefined (all-zero actuals)
        actual = positive[TARGET_COLUMN].to_numpy(dtype=np.float64)
        predicted = forecast(fit, positive["target_month"])
        mapes[str(well_id)] = float((np.abs(actual - predicted) / actual).mean() * 100.0)
    return pd.Series(mapes, dtype=float), fitted, failed


__all__ = [
    "ARPS_MIN_FITTED_SHARE",
    "EVALUATION_FILE",
    "EvaluationReport",
    "GateResult",
    "GateThresholds",
    "evaluate",
]
```

- [ ] **Step 4: Run para ver el pass**

Run: `cd apps/ml && .venv/bin/python -m pytest tests/unit/test_evaluation.py tests/unit/test_evaluation_metrics.py tests/unit/test_arps.py tests/unit/test_gates.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add apps/ml/src/petrocast_ml/evaluation/__init__.py apps/ml/tests/unit/test_evaluation.py
git commit -m "feat(ml): evaluate() orchestrator with gates over the test split [F3-15]"
```

---

### Task 6: Tracking de la evaluación en el mismo run MLflow

**Files:**

- Modify: `apps/ml/src/petrocast_ml/tracking.py`
- Test: `apps/ml/tests/unit/test_tracking.py` (extender)

**Interfaces:**

- Consumes: `EvaluationReport.to_mlflow_metrics()`, `.gates_passed`.
- Produces: `record_training_run(..., evaluation: EvaluationReport | None = None)`; constante `GATES_PASSED_TAG = "gates_passed"`.

- [ ] **Step 1: Failing tests** (agregar a `test_tracking.py`)

```python
# imports nuevos arriba del archivo:
from petrocast_ml.evaluation import EvaluationReport, GateThresholds
from petrocast_ml.evaluation.gates import evaluate_gates
from petrocast_ml.tracking import GATES_PASSED_TAG


def _evaluation_report(*, passed: bool) -> EvaluationReport:
    ratio = 0.9 if passed else 1.5
    gates = evaluate_gates(
        mase_median=0.8 if passed else 1.4,
        naive_mae_ratio=ratio,
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
```

- [ ] **Step 2: Run para ver el fail**

Run: `cd apps/ml && .venv/bin/python -m pytest tests/unit/test_tracking.py -v`
Expected: FAIL — `ImportError: cannot import name 'GATES_PASSED_TAG'`

- [ ] **Step 3: Implementación** (diff sobre `tracking.py`)

Import nuevo y constante junto a los tags de contrato C:

```python
from petrocast_ml.evaluation.report import EvaluationReport

#: Tag set by F3-15: whether the run's candidate passed the blocking gates —
#: what champion promotion (#16) checks before touching the alias.
GATES_PASSED_TAG = "gates_passed"
```

Firma y cuerpo de `record_training_run` (parámetro nuevo al final; docstring: sumar
"and, when an evaluation ran, its ``eval_*`` metrics plus the gate tag"):

```python
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
    ...
    with client.start_run(run_name=run_name):
        client.set_tags(_contract_c_tags(run_metadata))
        client.log_parameters(_run_parameters(request, result, dataset))
        client.log_metrics(dict(result.metrics))
        if evaluation is not None:
            client.log_metrics(evaluation.to_mlflow_metrics())
            client.set_tags({GATES_PASSED_TAG: str(evaluation.gates_passed).lower()})
        client.log_artifacts(artifact_dir)
    return run_name
```

Agregar `"GATES_PASSED_TAG"` a `__all__`.

- [ ] **Step 4: Run para ver el pass**

Run: `cd apps/ml && .venv/bin/python -m pytest tests/unit/test_tracking.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/ml/src/petrocast_ml/tracking.py apps/ml/tests/unit/test_tracking.py
git commit -m "feat(ml): log evaluation metrics and gate tag on the training run [F3-15]"
```

---

### Task 7: Wiring del CLI + smokes de exit code

**Files:**

- Modify: `apps/ml/src/petrocast_ml/training/__main__.py`
- Modify: `apps/ml/README.md` (sección corta de evaluación/gates)
- Test: `apps/ml/tests/smoke/test_evaluation_cli.py`

**Interfaces:**

- Consumes: `evaluate`, `EVALUATION_FILE`, `EvaluationReport`.
- Produces: CLI que siempre evalúa tras entrenar; stdout JSON con claves nuevas `evaluation` (payload de `to_dict()`) y `gates_passed`; `evaluation.json` en el artifact dir; exit code 1 cuando `gates_passed` es falso.

- [ ] **Step 1: Failing tests**

```python
"""CLI smokes: evaluation artifacts, stdout contract and gate exit codes.

The success-path smoke asserts *consistency* (exit code mirrors the verdict,
JSON on disk mirrors stdout) because the real-model verdict on fixtures is
data-dependent. The failure path is forced deterministically: test-month
actuals are rewritten to equal each well's last pre-cutoff value, making the
persistence naive perfect (aggregate naive MAE = 0), which an imperfect model
cannot match — gate 2 must fail and the CLI must exit 1.
"""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from petrocast_ml.evaluation import EVALUATION_FILE

CUTOFF = pd.Timestamp("2026-01-01")


def _run_cli(fixtures: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "petrocast_ml.training",
            "--features-csv",
            str(fixtures / "well_features.csv"),
            "--production-csv",
            str(fixtures / "production_monthly.csv"),
            "--as-of",
            "2026-01-01",
            "--horizons",
            "1,2,3",
            "--output-dir",
            str(tmp_path / "artifact"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_writes_report_and_exit_code_mirrors_verdict(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    completed = _run_cli(fixtures_dir, tmp_path)
    payload = json.loads(completed.stdout)

    report_path = Path(payload["artifact_dir"]) / EVALUATION_FILE
    assert report_path.exists()
    assert json.loads(report_path.read_text()) == payload["evaluation"]
    assert payload["gates_passed"] is payload["evaluation"]["gates_passed"]
    assert completed.returncode == (0 if payload["gates_passed"] else 1), completed.stderr


def test_cli_exits_1_when_the_naive_is_unbeatable(
    fixtures_dir: Path, production_monthly: pd.DataFrame, tmp_path: Path
) -> None:
    #

    last_before_cutoff = (
        production_monthly.loc[production_monthly["production_month"] < CUTOFF]
        .sort_values("production_month")
        .groupby("well_id")["oil_prod_m3"]
        .last()
    )
    rigged = production_monthly.copy()
    test_rows = rigged["production_month"] >= CUTOFF
    rigged.loc[test_rows, "oil_prod_m3"] = (
        rigged.loc[test_rows, "well_id"].map(last_before_cutoff).to_numpy()
    )

    rigged_dir = tmp_path / "rigged"
    rigged_dir.mkdir()
    rigged.to_csv(rigged_dir / "production_monthly.csv", index=False)
    (rigged_dir / "well_features.csv").write_text(
        (fixtures_dir / "well_features.csv").read_text()
    )

    completed = _run_cli(rigged_dir, tmp_path)
    payload = json.loads(completed.stdout)
    assert payload["gates_passed"] is False
    assert completed.returncode == 1
```

- [ ] **Step 2: Run para ver el fail**

Run: `cd apps/ml && .venv/bin/python -m pytest tests/smoke/test_evaluation_cli.py -v`
Expected: FAIL — `KeyError: 'evaluation'` (el stdout actual no trae esas claves)

- [ ] **Step 3: Implementación**

`__main__.py` — imports nuevos:

```python
from petrocast_ml.evaluation import EVALUATION_FILE, evaluate
```

Docstring del módulo: sumar al final "Every run is backtested (F3-15): the
evaluation report lands next to the artifact and a failed blocking gate turns
into exit code 1 — the promotion chain must not see the run as green."

En `main()`, después de `save_training_artifact(...)` y antes del bloque `--track`:

```python
    report = evaluate(result.model, dataset, production, request=request)
    (artifact_dir / EVALUATION_FILE).write_text(json.dumps(report.to_dict(), indent=2))
```

El bloque `--track` pasa la evaluación al run:

```python
        tracked_run = record_training_run(
            create_tracking_client(),
            request=request,
            result=result,
            dataset=dataset,
            run_metadata=run_metadata,
            artifact_dir=artifact_dir,
            evaluation=report,
        )
```

El print final y el exit code:

```python
    print(
        json.dumps(
            {
                "artifact_dir": str(artifact_dir),
                "metrics": dict(result.metrics),
                "evaluation": report.to_dict(),
                "gates_passed": report.gates_passed,
                "tracked_run": tracked_run,
            }
        )
    )
    if not report.gates_passed:
        raise SystemExit(1)
```

`README.md` de apps/ml — agregar sección tras la de training (ajustar al estilo
existente del README al ejecutar):

```markdown
## Evaluación y gates (F3-15)

Cada corrida de `python -m petrocast_ml.training` backtestea el modelo sobre el
cutoff single-origin (contrato F, ADR-0030): MAE/RMSE/MASE + MAPE-no-cero en
distribución (p50/p75/p90) contra naive (gate bloqueante) y Arps best-effort
(informativo). El reporte queda en `evaluation.json` junto al artifact y, con
`--track`, como métricas `eval_*` + tag `gates_passed` en el mismo run MLflow.
Si un gate bloqueante falla (mediana MASE ≥ 1 o MAE > naive), el proceso
termina con exit code 1: un run rojo no es promovible (#16).
```

- [ ] **Step 4: Run para ver el pass**

Run: `cd apps/ml && .venv/bin/python -m pytest tests/smoke -v`
Expected: PASS (smokes nuevos + existentes)

- [ ] **Step 5: Commit**

```bash
git add apps/ml/src/petrocast_ml/training/__main__.py apps/ml/README.md apps/ml/tests/smoke/test_evaluation_cli.py
git commit -m "feat(ml): wire backtesting gates into the training CLI [F3-15]"
```

---

### Task 8: Verificación completa y PR

**Files:** ninguno nuevo.

- [ ] **Step 1: Suite completa + linters + tipos**

Run: `cd apps/ml && .venv/bin/python -m pytest tests -v && .venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests && .venv/bin/mypy`
Expected: todo verde. Arreglar lo que salga antes de seguir.

- [ ] **Step 2: Verificación end-to-end real (skill verify)**

Correr el CLI real sobre fixtures con `--track` apuntando a un file store temporal y
revisar que el run MLflow tenga métricas `eval_*` y el tag:

```bash
cd apps/ml && MLFLOW_TRACKING_URI=file:///tmp/mlruns-f3-15 .venv/bin/python -m petrocast_ml.training \
  --features-csv tests/fixtures/well_features.csv \
  --production-csv tests/fixtures/production_monthly.csv \
  --as-of 2026-01-01 --horizons 1,2,3 --output-dir /tmp/f3-15-artifact --track; echo "exit=$?"
```

Expected: JSON con `evaluation` + `gates_passed`; `exit=` coherente; `evaluation.json` en el output dir.

- [ ] **Step 3: Push + PR**

```bash
git push -u origin feat/f3-15-model-evaluation-gates
gh pr create --title "feat(ml): evaluación, backtesting y gates de calidad [F3-15]" --body "... Closes #118 ..."
```

Monitorear CI en background y reportar.
