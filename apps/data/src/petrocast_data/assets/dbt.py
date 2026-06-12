from collections.abc import Iterator
from pathlib import Path

from dagster import AssetExecutionContext
from dagster_dbt import DbtCliResource, dbt_assets

DBT_PROJECT_DIR = Path(__file__).resolve().parents[3] / "dbt"
DBT_MANIFEST = DBT_PROJECT_DIR / "target" / "manifest.json"


@dbt_assets(manifest=DBT_MANIFEST, select="tag:f2_10_scaffold")
def dbt_smoke_assets(
    context: AssetExecutionContext,
    dbt: DbtCliResource,
) -> Iterator[object]:
    """Run the scaffold dbt model and tests against the warehouse."""
    yield from dbt.cli(["build"], context=context).stream()
