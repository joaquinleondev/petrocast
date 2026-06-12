{{ config(materialized="table", schema="silver", tags=["f2_10_scaffold"]) }}

select
    cast(event_id as integer) as event_id,
    cast(well_id as text) as well_id,
    cast(production_month as date) as production_month,
    cast(oil_m3 as numeric) as oil_m3,
    cast(_dlt_load_id as text) as dlt_load_id
from {{ source("bronze", "smoke_events") }}
