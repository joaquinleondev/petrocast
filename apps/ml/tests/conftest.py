"""Shared fixtures for the offline ML test datasets (F3-10).

The CSVs under ``tests/fixtures`` are small, hand-verifiable datasets that let
training (F3-13), backtesting (F3-15) and inference (F3-18) smokes run in CI
with no database, MLflow server or internet access. They are aligned with the
frozen contracts:

- **Contract A (ADR-0031):** ``well_features.csv`` mirrors the projection of
  ``features.well_features`` that ML consumers read — one row per
  ``(well_id, as_of_date)``, every feature computed exclusively from
  production months strictly before ``as_of_date`` (point-in-time rule),
  volumes in m³. The surrogate ``feature_key`` is not part of the projection.
- **Contract F (ADR-0030):** ``expected_training_dataset.csv`` and
  ``expected_naive_backtest.csv`` freeze the target/horizon convention:
  ``as_of_date`` is the first unknown month, so horizon ``h`` targets month
  ``as_of_date + (h - 1)`` ("train through M, predict M+1 … M+h"). Months
  without an observed actual produce no row (no imputed targets).

The four wells cover the portfolio shapes the model must handle: a mature
declining well with shut-in zero months (70001), a well with calendar gaps and
a stale tail (70002), a cold-start well below the 12-month eligibility
threshold (70003), and a mostly-zero intermittent well (70004 — the MASE zero
edge). ``well_id`` is always read as text, matching the idpozo grain.
"""

from pathlib import Path

import pandas as pd
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def production_monthly() -> pd.DataFrame:
    """Monthly oil production series (m³) at (well_id, production_month) grain."""
    return pd.read_csv(
        FIXTURES_DIR / "production_monthly.csv",
        dtype={"well_id": str},
        parse_dates=["production_month"],
    )


@pytest.fixture
def well_features() -> pd.DataFrame:
    """Contract A projection: persisted feature vectors per (well_id, as_of_date)."""
    return pd.read_csv(
        FIXTURES_DIR / "well_features.csv",
        dtype={"well_id": str},
        parse_dates=["as_of_date", "last_observed_month"],
    )


@pytest.fixture
def expected_training_dataset() -> pd.DataFrame:
    """Expected training rows for the smoke cutoff: target at as_of + (h - 1)."""
    return pd.read_csv(
        FIXTURES_DIR / "expected_training_dataset.csv",
        dtype={"well_id": str},
        parse_dates=["as_of_date", "target_month"],
    )


@pytest.fixture
def expected_naive_backtest() -> pd.DataFrame:
    """Expected persistence-baseline forecasts plus the in-sample MASE denominator."""
    return pd.read_csv(
        FIXTURES_DIR / "expected_naive_backtest.csv",
        dtype={"well_id": str},
        parse_dates=["as_of_date", "target_month"],
    )
