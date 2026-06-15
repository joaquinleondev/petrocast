import json
from collections.abc import Iterator
from pathlib import Path

from dagster import AssetExecutionContext, MonthlyPartitionsDefinition
from dagster_dbt import DbtCliResource, dbt_assets

DBT_PROJECT_DIR = Path(__file__).resolve().parents[3] / "dbt"
DBT_MANIFEST = DBT_PROJECT_DIR / "target" / "manifest.json"

# Silver is partitioned by production month (derived from the data's anio/mes),
# matching the medallion strategy in ADR-0026. Rematerializing a partition (or a
# range, e.g. backfill) reruns dbt for that window; the model's delete+insert
# keyed on production_month makes the rerun idempotent.
SILVER_MONTHLY_PARTITIONS = MonthlyPartitionsDefinition(start_date="2006-01-01")


@dbt_assets(manifest=DBT_MANIFEST, select="tag:f2_10_scaffold")
def dbt_smoke_assets(
    context: AssetExecutionContext,
    dbt: DbtCliResource,
) -> Iterator[object]:
    """Run the scaffold dbt model and tests against the warehouse."""
    yield from dbt.cli(["build"], context=context).stream()


@dbt_assets(
    manifest=DBT_MANIFEST,
    select="tag:silver",
    partitions_def=SILVER_MONTHLY_PARTITIONS,
)
def silver_dbt_assets(
    context: AssetExecutionContext,
    dbt: DbtCliResource,
) -> Iterator[object]:
    """Build the Silver models and tests for the partitioned production month.

    The partition's time window is passed to dbt as `min_month`/`max_month` so
    `silver_production` rebuilds only that month (delete+insert -> idempotent).
    """
    time_window = context.partition_time_window
    dbt_vars = {
        "min_month": time_window.start.strftime("%Y-%m-%d"),
        "max_month": time_window.end.strftime("%Y-%m-%d"),
    }
    yield from dbt.cli(["build", "--vars", json.dumps(dbt_vars)], context=context).stream()


@dbt_assets(
    manifest=DBT_MANIFEST,
    select="tag:gold",
    partitions_def=SILVER_MONTHLY_PARTITIONS,
)
def gold_dbt_assets(
    context: AssetExecutionContext,
    dbt: DbtCliResource,
) -> Iterator[object]:
    """Build the Gold star-schema models for the partitioned production month.

    The partition's time window is passed to dbt as `min_month`/`max_month` so
    `fact_production` rebuilds only that month (delete+insert -> idempotent),
    using the same backfill-by-range mechanism as Silver.
    """
    time_window = context.partition_time_window
    dbt_vars = {
        "min_month": time_window.start.strftime("%Y-%m-%d"),
        "max_month": time_window.end.strftime("%Y-%m-%d"),
    }
    yield from dbt.cli(["build", "--vars", json.dumps(dbt_vars)], context=context).stream()
