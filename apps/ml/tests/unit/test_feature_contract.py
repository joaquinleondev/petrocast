"""Contract A as code (F3-11): the frame ML reads must validate loudly."""

import pandas as pd
import pytest

from petrocast_ml import CONTRACT_COLUMNS, FEATURE_SCHEMA, KEY_COLUMNS, validate_feature_frame


class TestValidateFeatureFrame:
    def test_fixture_projection_satisfies_contract(self, well_features: pd.DataFrame) -> None:
        """The committed fixture IS the contract projection training/inference read."""
        validated = validate_feature_frame(well_features)
        assert list(validated.columns) == list(CONTRACT_COLUMNS)

    def test_missing_column_fails_loudly(self, well_features: pd.DataFrame) -> None:
        broken = well_features.drop(columns=["oil_prod_m3_trend_6m"])
        with pytest.raises(ValueError, match=r"missing columns.*oil_prod_m3_trend_6m"):
            validate_feature_frame(broken)

    def test_unexpected_column_fails_loudly(self, well_features: pd.DataFrame) -> None:
        """Schema drift between store and model must not pass silently (ADR-0031)."""
        drifted = well_features.assign(oil_prod_m3_lag_24m=1.0)
        with pytest.raises(ValueError, match=r"unexpected columns.*oil_prod_m3_lag_24m"):
            validate_feature_frame(drifted)

    def test_wrong_dtype_fails_loudly(self, well_features: pd.DataFrame) -> None:
        broken = well_features.assign(
            oil_prod_m3_lag_1m=lambda df: df["oil_prod_m3_lag_1m"].astype(str)
        )
        with pytest.raises(ValueError, match=r"oil_prod_m3_lag_1m.*expected numeric"):
            validate_feature_frame(broken)

    def test_duplicated_key_fails_loudly(self, well_features: pd.DataFrame) -> None:
        duplicated = pd.concat([well_features, well_features.iloc[[0]]], ignore_index=True)
        with pytest.raises(ValueError, match="duplicated"):
            validate_feature_frame(duplicated)

    def test_key_and_feature_columns_are_disjoint(self) -> None:
        assert not set(KEY_COLUMNS) & set(FEATURE_SCHEMA)
