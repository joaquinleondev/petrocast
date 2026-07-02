"""Dataset assembly and temporal split against the F3-10 frozen expectations."""

from datetime import date

import pandas as pd
import pytest

from petrocast_ml.training import (
    NAIVE_COLUMN,
    TARGET_COLUMN,
    TrainingRequest,
    build_training_dataset,
    temporal_split,
)

SMOKE_AS_OF = pd.Timestamp("2026-01-01")


@pytest.fixture
def dataset(production_monthly: pd.DataFrame, well_features: pd.DataFrame) -> pd.DataFrame:
    return build_training_dataset(well_features, production_monthly, horizons=(1, 2, 3))


class TestBuildTrainingDataset:
    def test_matches_frozen_expected_dataset(
        self, dataset: pd.DataFrame, expected_training_dataset: pd.DataFrame
    ) -> None:
        """The builder reproduces expected_training_dataset.csv exactly (contract F)."""
        got = (
            dataset.loc[dataset["as_of_date"] == SMOKE_AS_OF]
            .loc[:, ["well_id", "as_of_date", "horizon", "target_month", TARGET_COLUMN]]
            .sort_values(["well_id", "horizon"])
            .reset_index(drop=True)
        )
        want = (
            expected_training_dataset.astype({TARGET_COLUMN: float})
            .sort_values(["well_id", "horizon"])
            .reset_index(drop=True)
        )
        pd.testing.assert_frame_equal(got, want, check_dtype=False)

    def test_naive_matches_frozen_backtest(
        self, dataset: pd.DataFrame, expected_naive_backtest: pd.DataFrame
    ) -> None:
        """Persistence baseline per row equals the frozen backtest expectations."""
        got = dataset.loc[dataset["as_of_date"] == SMOKE_AS_OF].rename(
            columns={NAIVE_COLUMN: "got_naive_m3"}
        )
        merged = expected_naive_backtest.merge(
            got, on=["well_id", "as_of_date", "horizon", "target_month"], how="left"
        )
        assert merged["got_naive_m3"].notna().all()
        assert merged["got_naive_m3"].tolist() == pytest.approx(
            merged["naive_forecast_m3"].tolist()
        )

    def test_horizons_outside_contract_f_rejected(
        self, production_monthly: pd.DataFrame, well_features: pd.DataFrame
    ) -> None:
        with pytest.raises(ValueError, match=r"1\.\.12"):
            build_training_dataset(well_features, production_monthly, horizons=(0, 1))
        with pytest.raises(ValueError, match=r"1\.\.12"):
            build_training_dataset(well_features, production_monthly, horizons=(13,))


class TestTemporalSplit:
    def test_single_origin_split_is_chronological(self, dataset: pd.DataFrame) -> None:
        request = TrainingRequest(as_of_date=date(2026, 1, 1), features_version="fixtures")
        split = temporal_split(dataset, request=request)

        assert (split.test["as_of_date"] == SMOKE_AS_OF).all()
        assert split.train["as_of_date"].max() < SMOKE_AS_OF
        assert len(split.validation) == 0
        assert len(split.train) + len(split.test) == len(dataset)

    def test_missing_cutoff_rejected(self, dataset: pd.DataFrame) -> None:
        request = TrainingRequest(as_of_date=date(2030, 1, 1), features_version="fixtures")
        with pytest.raises(ValueError, match="no dataset rows"):
            temporal_split(dataset, request=request)

    def test_no_older_cutoffs_rejected(self, dataset: pd.DataFrame) -> None:
        """The oldest cutoff cannot be the evaluation origin: nothing left to train on."""
        request = TrainingRequest(as_of_date=date(2025, 12, 1), features_version="fixtures")
        with pytest.raises(ValueError, match="no training cutoffs"):
            temporal_split(dataset, request=request)
