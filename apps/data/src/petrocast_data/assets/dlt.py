from collections.abc import Iterator
from datetime import date

import dlt
from dagster import AssetExecutionContext
from dagster_dlt import DagsterDltResource, dlt_assets

from petrocast_data.settings import settings


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
