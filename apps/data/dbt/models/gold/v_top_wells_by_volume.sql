{{
    config(
        materialized="view",
        schema="gold",
        tags=["gold"],
    )
}}

-- Semantic layer (F2-28): centralizes the "top wells by volume" metric for
-- Metabase. Aggregates lifetime production per well from fact_production and ranks
-- by total oil; gas and water totals are exposed alongside. Fluids are not summed
-- together because the units differ (oil/water in m3, gas in Mm3).

with totals as (

    select
        fact.well_key,
        sum(fact.oil_prod_m3) as total_oil_m3,
        sum(fact.gas_prod_mm3) as total_gas_mm3,
        sum(fact.water_prod_m3) as total_water_m3
    from {{ ref("fact_production") }} as fact
    group by fact.well_key

)

select
    well.well_id,
    well.well_alias,
    well.field,
    well.basin,
    well.province,
    totals.total_oil_m3,
    totals.total_gas_mm3,
    totals.total_water_m3,
    row_number() over (
        order by totals.total_oil_m3 desc nulls last
    ) as oil_volume_rank
from totals
inner join {{ ref("dim_well") }} as well on totals.well_key = well.well_key
