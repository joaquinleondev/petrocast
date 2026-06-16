{{
    config(
        materialized="view",
        schema="gold",
        tags=["gold"],
    )
}}

-- Semantic layer (F2-28): centralizes the "monthly production by well" metric for
-- Metabase. Denormalizes fact_production with its dimensions so the Query Builder
-- exposes friendly well/company/period attributes next to the three measures,
-- without re-deriving the fact->dim joins in every question.

select
    period.production_month,
    period.year,
    period.month,
    period.month_name,
    well.well_id,
    well.well_alias,
    well.field,
    well.basin,
    well.province,
    company.company_name,
    fact.oil_prod_m3,
    fact.gas_prod_mm3,
    fact.water_prod_m3
from {{ ref("fact_production") }} as fact
inner join {{ ref("dim_well") }} as well on fact.well_key = well.well_key
inner join {{ ref("dim_company") }} as company
    on fact.company_key = company.company_key
inner join {{ ref("dim_date") }} as period on fact.date_key = period.date_key
