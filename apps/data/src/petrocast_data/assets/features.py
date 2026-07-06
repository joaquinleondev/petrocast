import hashlib
import json
from collections.abc import Iterator, Mapping
from datetime import date
from pathlib import Path
from typing import Any, cast

import dagster as dg
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, dbt_assets
from psycopg.connection import Connection

from petrocast_data.assets.dbt import DBT_MANIFEST, DBT_PROJECT_DIR
from petrocast_data.settings import get_settings

FEATURE_ASSET_KEY = dg.AssetKey(["features", "well_features"])
FEATURE_MODEL_PATH = DBT_PROJECT_DIR / "models" / "features" / "well_features.sql"
FEATURE_MONTHLY_PARTITIONS = dg.MonthlyPartitionsDefinition(
    start_date="2006-01-01",
    end_offset=1,
)
FEATURE_BACKFILL_POLICY = dg.BackfillPolicy.multi_run(max_partitions_per_run=1)
FEATURE_HISTORY_START_OFFSET = -1200
FEATURE_RETRY_POLICY = dg.RetryPolicy(
    max_retries=3,
    delay=30,
    backoff=dg.Backoff.EXPONENTIAL,
)


class FeatureDagsterDbtTranslator(DagsterDbtTranslator):
    """Map each feature cutoff to every prior Gold production partition."""

    def get_partition_mapping(
        self,
        dbt_resource_props: Mapping[str, Any],
        dbt_parent_resource_props: Mapping[str, Any],
    ) -> dg.PartitionMapping | None:
        if (
            dbt_resource_props.get("name") == "well_features"
            and dbt_parent_resource_props.get("name") == "fact_production"
        ):
            return dg.TimeWindowPartitionMapping(
                start_offset=FEATURE_HISTORY_START_OFFSET,
                end_offset=-1,
                allow_nonexistent_upstream_partitions=True,
            )
        return None


def _feature_dbt_vars(partition_key: str) -> dict[str, str]:
    return {"as_of_date": partition_key}


def _feature_config_hash(dbt_vars: Mapping[str, str], model_path: Path) -> str:
    hasher = hashlib.sha256(usedforsecurity=False)
    hasher.update(json.dumps(dbt_vars, sort_keys=True).encode())
    hasher.update(model_path.read_bytes())
    return hasher.hexdigest()


def _feature_materialization_metadata(
    partition_key: str,
    dbt_vars: Mapping[str, str],
) -> dict[str, int | str | dg.MetadataValue]:
    cutoff = date.fromisoformat(partition_key)
    settings = get_settings()

    with (
        Connection.connect(settings.psycopg_dsn) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            select
                (
                    select count(*)
                    from features.well_features
                    where as_of_date = %s
                ),
                (
                    select min(production_month)
                    from gold.fact_production
                    where production_month < %s
                ),
                (
                    select max(production_month)
                    from gold.fact_production
                    where production_month < %s
                )
            """,
            (cutoff, cutoff, cutoff),
        )
        row = cursor.fetchone()

    if row is None:
        raise RuntimeError("feature materialization metadata query returned no row")

    row_count, source_date_start, source_date_end = cast(
        tuple[int, date | None, date | None],
        row,
    )
    return {
        "dagster/row_count": row_count,
        "as_of_date": partition_key,
        "source_date_start": source_date_start.isoformat() if source_date_start else "empty",
        "source_date_end": source_date_end.isoformat() if source_date_end else "empty",
        "dbt_vars": dg.MetadataValue.json(dict(dbt_vars)),
        "config_hash": _feature_config_hash(dbt_vars, FEATURE_MODEL_PATH),
    }


@dbt_assets(
    manifest=DBT_MANIFEST,
    select="tag:features",
    dagster_dbt_translator=FeatureDagsterDbtTranslator(),
    partitions_def=FEATURE_MONTHLY_PARTITIONS,
    backfill_policy=FEATURE_BACKFILL_POLICY,
    retry_policy=FEATURE_RETRY_POLICY,
)
def feature_dbt_assets(
    context: dg.AssetExecutionContext,
    dbt: DbtCliResource,
) -> Iterator[object]:
    """Materialize the point-in-time feature store for one monthly cutoff."""
    partition_key = context.partition_key
    dbt_vars = _feature_dbt_vars(partition_key)
    context.log.info("Materializing feature store for as_of_date=%s", partition_key)

    events = dbt.cli(
        ["build", "--vars", json.dumps(dbt_vars)],
        context=context,
    ).stream()
    for event in events:
        if isinstance(event, dg.Output):
            metadata = _feature_materialization_metadata(partition_key, dbt_vars)
            context.log.info(
                "Materialized %s feature rows for as_of_date=%s",
                metadata["dagster/row_count"],
                partition_key,
            )
            yield event.with_metadata({**event.metadata, **metadata})
        else:
            yield event
