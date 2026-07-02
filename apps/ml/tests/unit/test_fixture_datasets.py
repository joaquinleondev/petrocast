"""Consistency tests for the offline ML fixtures (F3-10).

These tests are executable documentation of the assumptions the fixtures
encode. If a fixture is edited by hand and drifts from contract A (ADR-0031)
or contract F (ADR-0030), they fail and point at the exact divergence.
"""

import math

import pandas as pd
import pytest

SMOKE_AS_OF = pd.Timestamp("2026-01-01")
MAX_HORIZON = 12
ELIGIBILITY_MIN_MONTHS = 12  # ADR-0030: wells below this are excluded from gates
MAX_FIXTURE_BYTES = 64_000


def known_before(production: pd.DataFrame, well_id: str, as_of: pd.Timestamp) -> pd.DataFrame:
    """Point-in-time slice: production strictly before the knowledge cutoff."""
    mask = (production["well_id"] == well_id) & (production["production_month"] < as_of)
    return production.loc[mask].sort_values("production_month")


class TestProductionCoverage:
    """The raw series must cover the portfolio shapes ADR-0030 calls out."""

    def test_has_multiple_wells_and_zero_months(self, production_monthly: pd.DataFrame) -> None:
        assert production_monthly["well_id"].nunique() >= 4
        assert (production_monthly["oil_prod_m3"] == 0).any(), "shut-in zeros required for MASE"

    def test_has_calendar_gaps(self, production_monthly: pd.DataFrame) -> None:
        """At least one well misses months inside its own observed range."""
        has_gap = False
        for _, series in production_monthly.groupby("well_id"):
            months = series["production_month"].sort_values()
            spanned = pd.date_range(months.iloc[0], months.iloc[-1], freq="MS")
            has_gap |= len(spanned) > len(months)
        assert has_gap

    def test_has_cold_start_and_mature_wells(self, production_monthly: pd.DataFrame) -> None:
        history = {
            str(well_id): len(known_before(production_monthly, str(well_id), SMOKE_AS_OF))
            for well_id in production_monthly["well_id"].unique()
        }
        assert any(n < ELIGIBILITY_MIN_MONTHS for n in history.values()), "cold-start well missing"
        assert any(n >= 24 for n in history.values()), "mature well missing"


class TestWellFeaturesContractA:
    """well_features.csv must equal a point-in-time recomputation from the series."""

    def test_key_is_unique(self, well_features: pd.DataFrame) -> None:
        assert not well_features.duplicated(["well_id", "as_of_date"]).any()

    def test_features_recompute_from_production(
        self, production_monthly: pd.DataFrame, well_features: pd.DataFrame
    ) -> None:
        for row in well_features.itertuples():
            known = known_before(production_monthly, str(row.well_id), row.as_of_date)
            assert len(known) > 0, "feature rows only exist for wells with history"
            by_month = dict(zip(known["production_month"], known["oil_prod_m3"], strict=False))

            for k, got in (
                (1, row.oil_prod_m3_lag_1m),
                (2, row.oil_prod_m3_lag_2m),
                (3, row.oil_prod_m3_lag_3m),
                (6, row.oil_prod_m3_lag_6m),
                (12, row.oil_prod_m3_lag_12m),
            ):
                want = by_month.get(row.as_of_date - pd.DateOffset(months=k))
                if want is None:
                    assert math.isnan(got), f"lag_{k}m must be null when the month is unobserved"
                else:
                    assert got == pytest.approx(want)

            def window(k: int, known: pd.DataFrame = known, row=row) -> pd.DataFrame:
                return known.loc[
                    known["production_month"] >= row.as_of_date - pd.DateOffset(months=k)
                ]

            for k, got in (
                (3, row.oil_prod_m3_roll_mean_3m),
                (6, row.oil_prod_m3_roll_mean_6m),
                (12, row.oil_prod_m3_roll_mean_12m),
            ):
                # Missing months are excluded from the mean, not imputed as zero.
                assert got == pytest.approx(window(k)["oil_prod_m3"].mean(), rel=1e-4)

            for k, got in ((6, row.oil_prod_m3_roll_std_6m), (12, row.oil_prod_m3_roll_std_12m)):
                want_std = window(k)["oil_prod_m3"].std(ddof=1)  # sample std, like stddev
                if math.isnan(want_std):
                    assert math.isnan(got), f"roll_std_{k}m needs >= 2 observed months"
                else:
                    assert got == pytest.approx(want_std, rel=1e-4)

            for k, got in ((6, row.oil_prod_m3_trend_6m), (12, row.oil_prod_m3_trend_12m)):
                frame = window(k)
                if len(frame) < 2:
                    assert math.isnan(got), f"trend_{k}m needs >= 2 observed months"
                    continue
                # Least-squares slope vs calendar month index == Postgres regr_slope.
                months = frame["production_month"]
                x = (months.dt.year * 12 + months.dt.month).astype(float)
                y = frame["oil_prod_m3"].astype(float)
                slope = ((x - x.mean()) * (y - y.mean())).sum() / ((x - x.mean()) ** 2).sum()
                assert got == pytest.approx(slope, rel=1e-4)

            zero_12 = int((window(12)["oil_prod_m3"] == 0).sum())
            assert row.zero_months_12m == zero_12

            assert row.months_with_history == len(known)
            first = known["production_month"].iloc[0]
            last = known["production_month"].iloc[-1]
            age = (row.as_of_date.year - first.year) * 12 + (row.as_of_date.month - first.month)
            since = (row.as_of_date.year - last.year) * 12 + (row.as_of_date.month - last.month)
            assert row.well_age_months == age
            assert row.months_since_last_observed == since
            assert row.last_observed_month == last

    def test_static_attributes_present(self, well_features: pd.DataFrame) -> None:
        """Cold-start features (ADR-0030): every row carries the dim_well statics."""
        assert well_features[["basin", "field", "resource_type"]].notna().all().all()


class TestTrainingDatasetContractF:
    """Target/horizon convention: as_of_date is the first unknown month.

    ADR-0030 phrases it as "train with data through month M, predict
    M+1 … M+h"; with as_of_date = M+1 that means horizon h targets month
    as_of_date + (h - 1). Unobserved target months yield no row.
    """

    def test_horizons_within_phase_3_bounds(self, expected_training_dataset: pd.DataFrame) -> None:
        assert expected_training_dataset["horizon"].between(1, MAX_HORIZON).all()

    def test_target_month_convention(self, expected_training_dataset: pd.DataFrame) -> None:
        for row in expected_training_dataset.itertuples():
            assert row.target_month == row.as_of_date + pd.DateOffset(months=row.horizon - 1)

    def test_targets_match_observed_production(
        self, production_monthly: pd.DataFrame, expected_training_dataset: pd.DataFrame
    ) -> None:
        observed = {
            (row.well_id, row.production_month): row.oil_prod_m3
            for row in production_monthly.itertuples()
        }
        expected = expected_training_dataset.set_index(["well_id", "target_month"])
        for key, target in expected["oil_prod_m3_target"].items():
            assert target == pytest.approx(observed[key])

    def test_unobserved_target_months_are_excluded(
        self, production_monthly: pd.DataFrame, expected_training_dataset: pd.DataFrame
    ) -> None:
        """Every (well, horizon) with an observed actual is present; none other."""
        horizons = sorted(expected_training_dataset["horizon"].unique())
        expected_keys = {
            (row.well_id, int(row.horizon)) for row in expected_training_dataset.itertuples()
        }
        derived_keys = set()
        for well_id in production_monthly["well_id"].unique():
            months = set(
                production_monthly.loc[production_monthly["well_id"] == well_id, "production_month"]
            )
            for h in horizons:
                if SMOKE_AS_OF + pd.DateOffset(months=h - 1) in months:
                    derived_keys.add((str(well_id), h))
        assert expected_keys == derived_keys


class TestNaiveBacktestBaseline:
    """Persistence baseline (ADR-0030): last observed value before the cutoff,
    sustained over the whole horizon, plus the MASE denominator — the
    in-sample MAE of the one-step naive (Hyndman). With calendar gaps, the
    one-step diff is taken between consecutive *observed* months.
    """

    def test_naive_is_last_observed_value(
        self, production_monthly: pd.DataFrame, expected_naive_backtest: pd.DataFrame
    ) -> None:
        for row in expected_naive_backtest.itertuples():
            known = known_before(production_monthly, str(row.well_id), row.as_of_date)
            assert row.naive_forecast_m3 == pytest.approx(known["oil_prod_m3"].iloc[-1])

    def test_actuals_match_observed_production(
        self, production_monthly: pd.DataFrame, expected_naive_backtest: pd.DataFrame
    ) -> None:
        observed = {
            (row.well_id, row.production_month): row.oil_prod_m3
            for row in production_monthly.itertuples()
        }
        for row in expected_naive_backtest.itertuples():
            assert row.actual_m3 == pytest.approx(observed[(str(row.well_id), row.target_month)])

    def test_mase_denominator_is_insample_one_step_mae(
        self, production_monthly: pd.DataFrame, expected_naive_backtest: pd.DataFrame
    ) -> None:
        for row in expected_naive_backtest.itertuples():
            values = known_before(production_monthly, str(row.well_id), row.as_of_date)[
                "oil_prod_m3"
            ]
            insample_mae = values.diff().abs().iloc[1:].mean()
            assert insample_mae > 0, "an all-constant series would undefine MASE"
            assert row.naive_insample_mae_m3 == pytest.approx(insample_mae, rel=1e-4)

    def test_backtest_rows_mirror_training_rows(
        self,
        expected_training_dataset: pd.DataFrame,
        expected_naive_backtest: pd.DataFrame,
    ) -> None:
        key_cols = ["well_id", "as_of_date", "horizon", "target_month"]
        pd.testing.assert_frame_equal(
            expected_training_dataset[key_cols],
            expected_naive_backtest[key_cols],
        )


class TestFixtureHygiene:
    """No secrets, no heavy files (F3-10 acceptance criteria)."""

    def test_fixture_files_stay_small(self, fixtures_dir) -> None:
        csvs = sorted(fixtures_dir.glob("*.csv"))
        assert csvs, "fixtures directory must contain the committed CSVs"
        for path in csvs:
            assert path.stat().st_size < MAX_FIXTURE_BYTES, f"{path.name} too large for CI"
