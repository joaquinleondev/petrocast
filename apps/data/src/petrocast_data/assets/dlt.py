from collections.abc import Iterator
from datetime import date

import dagster as dg
import dlt
from dagster import AssetExecutionContext
from dagster_dlt import DagsterDltResource, build_dlt_asset_specs, dlt_assets

from petrocast_data.datos_gob_ar import read_csv_rows
from petrocast_data.settings import get_settings

BRONZE_MONTHLY_PARTITIONS = dg.MonthlyPartitionsDefinition(start_date="2006-01-01")
BRONZE_RETRY_POLICY = dg.RetryPolicy(
    max_retries=3,
    delay=30,
    backoff=dg.Backoff.EXPONENTIAL,
)


@dlt.source(name="petrocast_smoke")
def petrocast_smoke_source() -> object:
    """Small in-memory source that proves dlt can load into bronze."""

    @dlt.resource(name="smoke_events", write_disposition="replace", primary_key="event_id")
    def smoke_events() -> Iterator[dict[str, object]]:
        yield {
            "event_id": 1,
            "well_id": "F2-10-SMOKE",
            "production_month": date(2026, 6, 1).isoformat(),
            "oil_m3": 1.0,
        }

    return smoke_events


def petrocast_smoke_pipeline() -> dlt.Pipeline:
    settings = get_settings()
    return dlt.pipeline(
        pipeline_name="petrocast_smoke",
        destination=dlt.destinations.postgres(settings.dlt_destination_url),
        dataset_name="bronze",
    )


@dlt_assets(
    dlt_source=petrocast_smoke_source(),
    dlt_pipeline=petrocast_smoke_pipeline(),
    name="petrocast_smoke",
    group_name="bronze",
)
def petrocast_smoke_dlt_assets(
    context: AssetExecutionContext,
    dlt: DagsterDltResource,
) -> Iterator[object]:
    yield from dlt.run(context=context)


@dlt.source(name="petrocast_bronze")
def petrocast_bronze_source(partition_key: str | None = None) -> object:
    operational_partition = partition_key or date.today().replace(day=1).isoformat()

    @dlt.resource(name="production_by_well", write_disposition="replace")
    def production_by_well() -> Iterator[dict[str, object]]:
        settings = get_settings()
        yield from read_csv_rows(
            settings.source_production_url,
            source_name="production_by_well",
            partition_key=operational_partition,
        )

    @dlt.resource(name="wells_registry", write_disposition="replace")
    def wells_registry() -> Iterator[dict[str, object]]:
        settings = get_settings()
        yield from read_csv_rows(
            settings.source_wells_url,
            source_name="wells_registry",
            partition_key=operational_partition,
        )

    return [production_by_well, wells_registry]


def petrocast_bronze_pipeline() -> dlt.Pipeline:
    settings = get_settings()
    return dlt.pipeline(
        pipeline_name="petrocast_bronze",
        destination=dlt.destinations.postgres(settings.dlt_destination_url),
        dataset_name="bronze",
    )


@dg.multi_asset(
    name="petrocast_bronze",
    group_name="bronze",
    can_subset=True,
    partitions_def=BRONZE_MONTHLY_PARTITIONS,
    retry_policy=BRONZE_RETRY_POLICY,
    specs=build_dlt_asset_specs(
        dlt_source=petrocast_bronze_source(),
        dlt_pipeline=petrocast_bronze_pipeline(),
    ),
)
def petrocast_bronze_dlt_assets(
    context: AssetExecutionContext,
    dlt: DagsterDltResource,
) -> Iterator[object]:
    yield from dlt.run(
        context=context,
        dlt_source=petrocast_bronze_source(partition_key=context.partition_key),
        dlt_pipeline=petrocast_bronze_pipeline(),
    )
