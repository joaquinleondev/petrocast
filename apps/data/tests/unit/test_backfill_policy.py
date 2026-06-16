import dagster as dg

from petrocast_data.assets.dbt import gold_dbt_assets, silver_dbt_assets
from petrocast_data.assets.dlt import petrocast_bronze_dlt_assets


def test_partitioned_assets_support_cli_partition_range() -> None:
    expected_policy = dg.BackfillPolicy.single_run()

    for assets_def in (
        petrocast_bronze_dlt_assets,
        silver_dbt_assets,
        gold_dbt_assets,
    ):
        assert assets_def.backfill_policy == expected_policy
