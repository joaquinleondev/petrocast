from pathlib import Path

import dagster as dg
import pytest

DBT_MANIFEST = Path(__file__).resolve().parents[2] / "dbt" / "target" / "manifest.json"

if not DBT_MANIFEST.exists():
    pytest.skip(
        "dbt manifest not built (run `dbt parse`); exercised in CI after parse",
        allow_module_level=True,
    )

from petrocast_data.assets.features import (  # noqa: E402
    FEATURE_BACKFILL_POLICY,
    FEATURE_HISTORY_START_OFFSET,
    FEATURE_MONTHLY_PARTITIONS,
    FEATURE_RETRY_POLICY,
    FeatureDagsterDbtTranslator,
    _feature_config_hash,
    _feature_dbt_vars,
    feature_dbt_assets,
)


def test_feature_asset_materializes_one_month_per_run() -> None:
    assert feature_dbt_assets.partitions_def == FEATURE_MONTHLY_PARTITIONS
    assert feature_dbt_assets.backfill_policy == FEATURE_BACKFILL_POLICY
    assert dg.BackfillPolicy.multi_run(max_partitions_per_run=1) == FEATURE_BACKFILL_POLICY


def test_feature_asset_reuses_phase_two_retry_policy() -> None:
    assert feature_dbt_assets.op.retry_policy == FEATURE_RETRY_POLICY
    assert FEATURE_RETRY_POLICY.max_retries == 3
    assert FEATURE_RETRY_POLICY.delay == 30
    assert FEATURE_RETRY_POLICY.backoff == dg.Backoff.EXPONENTIAL


def test_feature_asset_depends_on_all_prior_gold_production_partitions() -> None:
    mapping = FeatureDagsterDbtTranslator().get_partition_mapping(
        {"name": "well_features"},
        {"name": "fact_production"},
    )

    assert mapping == dg.TimeWindowPartitionMapping(
        start_offset=FEATURE_HISTORY_START_OFFSET,
        end_offset=-1,
        allow_nonexistent_upstream_partitions=True,
    )


def test_feature_config_hash_captures_cutoff_and_model_sql(tmp_path: Path) -> None:
    model_path = tmp_path / "well_features.sql"
    model_path.write_text("select 1", encoding="utf-8")

    first_vars = _feature_dbt_vars("2015-06-01")
    first_hash = _feature_config_hash(first_vars, model_path)

    assert first_vars == {"as_of_date": "2015-06-01"}
    assert first_hash == _feature_config_hash(first_vars, model_path)
    assert first_hash != _feature_config_hash(_feature_dbt_vars("2015-07-01"), model_path)

    model_path.write_text("select 2", encoding="utf-8")
    assert first_hash != _feature_config_hash(first_vars, model_path)
