{{
    config(
        materialized="incremental",
        incremental_strategy="delete+insert",
        unique_key="production_key",
        schema="gold",
        tags=["gold"],
    )
}}

-- Silver -> Gold: monthly production fact (one row per well and production
-- month). The primary key `production_key` is a deterministic hash of
-- (well_id, production_month); foreign keys reuse the SAME surrogate-key
-- expressions as the dimensions so the joins resolve. delete+insert by
-- production_key keeps the fact idempotent on reprocess. The `min_month`/
-- `max_month` vars scope a backfill range, matching silver_production; the
-- partitioned Dagster asset passes them per partition.

with source as (

    select
        well_id,
        company_id,
        production_month,
        oil_prod_m3,
        gas_prod_mm3,
        water_prod_m3
    from {{ ref("silver_production") }}

)

select
    {{ dbt_utils.generate_surrogate_key(["well_id", "production_month"]) }} as production_key,
    {{ dbt_utils.generate_surrogate_key(["well_id"]) }} as well_key,
    {{ dbt_utils.generate_surrogate_key(["company_id"]) }} as company_key,
    {{ dbt_utils.generate_surrogate_key(["production_month"]) }} as date_key,
    well_id,
    production_month,
    oil_prod_m3,
    gas_prod_mm3,
    water_prod_m3
from source
where
    true
    {% if var("min_month", none) is not none %}
        and production_month >= cast('{{ var("min_month") }}' as date)
        and production_month < cast('{{ var("max_month") }}' as date)
    {% endif %}
