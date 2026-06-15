{{
    config(
        materialized="incremental",
        incremental_strategy="delete+insert",
        unique_key="date_key",
        schema="gold",
        tags=["gold"],
    )
}}

-- Silver -> Gold: date dimension at month grain (SCD Type 1, one row per month).
-- The surrogate key `date_key` is a deterministic hash of `production_month`;
-- delete+insert upserts by that key so reprocess does not duplicate rows.
-- Source: distinct production months in silver_production.

with source as (

    select distinct production_month
    from {{ ref("silver_production") }}
    where production_month is not null

)

select
    {{ dbt_utils.generate_surrogate_key(["production_month"]) }} as date_key,
    production_month,
    cast(extract(year from production_month) as integer) as year,  -- noqa: RF04
    cast(extract(month from production_month) as integer) as month,  -- noqa: RF04
    cast(extract(quarter from production_month) as integer) as quarter,  -- noqa: RF04
    trim(to_char(production_month, 'Month')) as month_name
from source
