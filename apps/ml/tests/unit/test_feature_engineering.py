"""Point-in-time tests for the feature definitions (F3-11, contract A).

ADR-0031 requires the PIT rule to be testable: no feature of a row with
cutoff ``d`` may change if the data after ``d`` is removed. These tests run
that exact experiment on the pandas mirror of the dbt model, and pin the
committed ``well_features.csv`` fixture (hand-verified against the SQL output)
to those definitions — so the SQL, the python mirror and the fixture cannot
drift apart silently.
"""

import pandas as pd
import pytest

from petrocast_ml.features import (
    FEATURE_TABLE_COLUMNS,
    STATIC_FEATURES,
    compute_well_features,
    validate_feature_frame,
)

FIXTURE_AS_OF = pd.Timestamp("2025-12-01")


@pytest.fixture
def well_attributes(well_features: pd.DataFrame) -> pd.DataFrame:
    """Static dim_well projection, as the fixture snapshot carries it."""
    return well_features.loc[:, ["well_id", *STATIC_FEATURES]]


class TestPointInTimeRule:
    """No feature of a cutoff-d row may look at production at or after d."""

    def test_features_unchanged_when_future_months_are_removed(
        self, production_monthly: pd.DataFrame, well_attributes: pd.DataFrame
    ) -> None:
        """The ADR-0031 experiment: recompute the cutoff without its future."""
        full = compute_well_features(
            production_monthly, as_of_date=FIXTURE_AS_OF, well_attributes=well_attributes
        )
        truncated_series = production_monthly.loc[
            production_monthly["production_month"] < FIXTURE_AS_OF
        ]
        truncated = compute_well_features(
            truncated_series, as_of_date=FIXTURE_AS_OF, well_attributes=well_attributes
        )
        pd.testing.assert_frame_equal(full, truncated)

    def test_features_unchanged_when_future_is_tampered(
        self, production_monthly: pd.DataFrame, well_attributes: pd.DataFrame
    ) -> None:
        """Injecting absurd post-cutoff months must not move a single value."""
        tampered_rows = pd.DataFrame(
            {
                "well_id": ["70001", "70003"],
                "production_month": [pd.Timestamp("2026-06-01"), pd.Timestamp("2025-12-01")],
                "oil_prod_m3": [1_000_000.0, 1_000_000.0],
            }
        )
        tampered = pd.concat([production_monthly, tampered_rows], ignore_index=True)
        baseline = compute_well_features(
            production_monthly, as_of_date=FIXTURE_AS_OF, well_attributes=well_attributes
        )
        recomputed = compute_well_features(
            tampered, as_of_date=FIXTURE_AS_OF, well_attributes=well_attributes
        )
        pd.testing.assert_frame_equal(baseline, recomputed)

    def test_wells_without_history_before_cutoff_produce_no_row(
        self, production_monthly: pd.DataFrame
    ) -> None:
        first_month = production_monthly["production_month"].min()
        features = compute_well_features(production_monthly, as_of_date=first_month)
        assert features.empty
        assert list(features.columns) == list(FEATURE_TABLE_COLUMNS)


class TestFixtureMirrorsDefinitions:
    """The committed contract A snapshot equals a recomputation from the series."""

    def test_fixture_equals_reference_recomputation(
        self,
        production_monthly: pd.DataFrame,
        well_features: pd.DataFrame,
        well_attributes: pd.DataFrame,
    ) -> None:
        recomputed = compute_well_features(
            production_monthly, as_of_date=FIXTURE_AS_OF, well_attributes=well_attributes
        )
        pd.testing.assert_frame_equal(
            recomputed,
            well_features.loc[:, list(FEATURE_TABLE_COLUMNS)],
            check_dtype=False,
            rtol=1e-4,
        )

    def test_fixture_passes_contract_validation(self, well_features: pd.DataFrame) -> None:
        validate_feature_frame(well_features)


class TestValidateFeatureFrame:
    def test_rejects_point_in_time_violation(self, well_features: pd.DataFrame) -> None:
        corrupted = well_features.copy()
        corrupted.loc[0, "last_observed_month"] = corrupted.loc[0, "as_of_date"]
        with pytest.raises(ValueError, match="point-in-time violation"):
            validate_feature_frame(corrupted)

    def test_rejects_duplicated_keys(self, well_features: pd.DataFrame) -> None:
        duplicated = pd.concat([well_features, well_features.iloc[[0]]], ignore_index=True)
        with pytest.raises(ValueError, match="duplicated"):
            validate_feature_frame(duplicated)

    def test_rejects_missing_columns(self, well_features: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="missing columns"):
            validate_feature_frame(well_features.drop(columns=["oil_prod_m3_trend_slope_6m"]))
