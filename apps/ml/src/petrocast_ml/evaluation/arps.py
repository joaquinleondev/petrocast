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


def _hyperbolic(t: NDArray[np.float64], qi: float, di: float, b: float) -> NDArray[np.float64]:
    return qi / np.power(1.0 + b * di * t, 1.0 / b)


def _months_since(months: pd.Series, origin: pd.Timestamp) -> NDArray[np.float64]:
    absolute = months.dt.year.to_numpy() * 12 + months.dt.month.to_numpy()
    return np.asarray(absolute - (origin.year * 12 + origin.month), dtype=np.float64)


def fit_well(production_train: pd.DataFrame) -> ArpsFit | None:
    """Fit one well's pre-cutoff series; ``None`` whenever it is not fittable."""
    observed = production_train.loc[production_train["oil_prod_m3"].notna()].sort_values(
        "production_month"
    )
    positive = observed.loc[observed["oil_prod_m3"] > 0]
    if len(positive) < MIN_POSITIVE_POINTS:
        return None

    t0 = pd.Timestamp(observed["production_month"].min())
    t = _months_since(positive["production_month"], t0)
    q = positive["oil_prod_m3"].to_numpy(dtype=np.float64)
    # observed is sorted by month above, so the tail is the most recent year — a
    # sane qi seed for curve_fit regardless of the row order the caller passed in.
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
