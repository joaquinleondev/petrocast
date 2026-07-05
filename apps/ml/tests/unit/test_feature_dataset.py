"""Tests for the model-ready frames built from persisted features (F3-11).

The output must be directly consumable by training (F3-13) and inference
(F3-18) under contract F (ADR-0030): horizon ``h`` targets month
``as_of_date + (h - 1)``, unobserved target months produce no training row,
and the model input frame is the frozen MODEL_INPUT_COLUMNS projection. The
expected values come from the hand-built F3-10 fixtures.
"""

import pandas as pd
import pytest

from petrocast_ml.features import (
    HORIZON_COLUMN,
    MODEL_INPUT_COLUMNS,
    STATIC_FEATURES,
    TARGET_COLUMN,
    TARGET_MONTH_COLUMN,
    as_model_input,
    build_inference_frame,
    build_training_dataset,
    compute_well_features,
)

TRAINING_AS_OF = pd.Timestamp("2026-01-01")
KEY_WITH_TARGET = ["well_id", "as_of_date", "horizon", "target_month"]


@pytest.fixture
def training_features(
    production_monthly: pd.DataFrame, well_features: pd.DataFrame
) -> pd.DataFrame:
    """Contract A rows for the training smoke cutoff of the F3-10 fixtures."""
    statics = well_features.loc[:, ["well_id", *STATIC_FEATURES]]
    return compute_well_features(
        production_monthly, as_of_date=TRAINING_AS_OF, well_attributes=statics
    )


class TestBuildTrainingDataset:
    def test_matches_expected_training_fixture(
        self,
        training_features: pd.DataFrame,
        production_monthly: pd.DataFrame,
        expected_training_dataset: pd.DataFrame,
    ) -> None:
        """Keys and targets reproduce the frozen contract F fixture exactly."""
        dataset = build_training_dataset(training_features, production_monthly)
        expected = expected_training_dataset.sort_values(
            ["well_id", "as_of_date", "horizon"], ignore_index=True
        )
        pd.testing.assert_frame_equal(
            dataset.loc[:, [*KEY_WITH_TARGET, TARGET_COLUMN]],
            expected.loc[:, [*KEY_WITH_TARGET, "oil_prod_m3_target"]],
            check_dtype=False,
        )

    def test_rows_carry_the_full_feature_projection(
        self, training_features: pd.DataFrame, production_monthly: pd.DataFrame
    ) -> None:
        dataset = build_training_dataset(training_features, production_monthly)
        for column in MODEL_INPUT_COLUMNS:
            assert column in dataset.columns

    def test_rejects_horizons_outside_contract_f(
        self, training_features: pd.DataFrame, production_monthly: pd.DataFrame
    ) -> None:
        with pytest.raises(ValueError, match=r"1\.\.12"):
            build_training_dataset(training_features, production_monthly, horizons=[0])
        with pytest.raises(ValueError, match=r"1\.\.12"):
            build_training_dataset(training_features, production_monthly, horizons=[13])


class TestBuildInferenceFrame:
    def test_expands_each_well_over_the_requested_horizon(
        self, training_features: pd.DataFrame
    ) -> None:
        frame = build_inference_frame(training_features, horizon=3)
        assert len(frame) == 3 * len(training_features)
        per_well = frame.loc[frame["well_id"] == frame["well_id"].iloc[0]]
        assert list(per_well[HORIZON_COLUMN]) == [1, 2, 3]
        for row in per_well.itertuples():
            expected_month = row.as_of_date + pd.DateOffset(months=row.horizon - 1)
            assert getattr(row, TARGET_MONTH_COLUMN) == expected_month

    def test_never_recomputes_features(self, training_features: pd.DataFrame) -> None:
        """Every horizon replica carries the identical persisted feature vector."""
        frame = build_inference_frame(training_features, horizon=2)
        for _, replicas in frame.groupby("well_id"):
            feature_only = replicas.loc[:, [c for c in MODEL_INPUT_COLUMNS if c != HORIZON_COLUMN]]
            assert len(feature_only.drop_duplicates()) == 1

    def test_rejects_horizon_outside_contract_f(self, training_features: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match=r"1\.\.12"):
            build_inference_frame(training_features, horizon=0)
        with pytest.raises(ValueError, match=r"1\.\.12"):
            build_inference_frame(training_features, horizon=13)


class TestAsModelInput:
    def test_projects_exactly_the_model_input_columns(
        self, training_features: pd.DataFrame, production_monthly: pd.DataFrame
    ) -> None:
        dataset = build_training_dataset(training_features, production_monthly)
        model_input = as_model_input(dataset)
        assert list(model_input.columns) == list(MODEL_INPUT_COLUMNS)

    def test_static_features_become_categoricals(self, training_features: pd.DataFrame) -> None:
        frame = build_inference_frame(training_features, horizon=1)
        model_input = as_model_input(frame)
        for column in STATIC_FEATURES:
            assert isinstance(model_input[column].dtype, pd.CategoricalDtype)
