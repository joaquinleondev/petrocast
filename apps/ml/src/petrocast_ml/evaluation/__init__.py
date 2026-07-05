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
    test[PREDICTION_COLUMN] = np.asarray(model.predict(prepare_model_input(test)), dtype=float)

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
