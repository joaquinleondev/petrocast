{{
    config(
        materialized="incremental",
        incremental_strategy="delete+insert",
        unique_key="feature_key",
        schema="features",
        tags=["features"],
    )
}}

-- Gold -> Features: feature store base table (contract A, ADR-0031). One row
-- per (well_id, as_of_date): what was known about the well at that knowledge
-- cutoff. Point-in-time rule: every feature is computed exclusively from
-- production months strictly BEFORE `as_of_date`, so a row materialized for a
-- past cutoff never leaks future data (training and backtesting stay honest).
-- The `as_of_date` var selects the partition to materialize (the Dagster asset
-- of F3-12 passes it per monthly partition); without it, the model builds the
-- latest cutoff available in gold (max production_month + 1 month). Cutoffs are
-- normalized to the first day of the month to align with the pozo-mes grain.
-- delete+insert by feature_key re-materializes a cutoff idempotently and leaves
-- every other cutoff untouched (immutable snapshots, ADR-0031). Volumes in m³.

with production as (

    select
        well_id,
        production_month,
        oil_prod_m3
    from {{ ref("fact_production") }}

),

cutoff as (

    {% if var("as_of_date", none) is not none %}
        select cast(date_trunc('month', cast('{{ var("as_of_date") }}' as date)) as date) as as_of_date
    {% else %}
        select cast(date_trunc('month', max(production_month) + interval '1 month') as date) as as_of_date
        from production
    {% endif %}

),

known as (

    select
        production.well_id,
        production.production_month,
        production.oil_prod_m3,
        cutoff.as_of_date
    from production
    cross join cutoff
    where production.production_month < cutoff.as_of_date

),

aggregated as (

    select
        well_id,
        as_of_date,
        max(case
            when production_month = cast(as_of_date - interval '1 month' as date) then oil_prod_m3
        end) as oil_prod_m3_lag_1m,
        max(case
            when production_month = cast(as_of_date - interval '2 months' as date) then oil_prod_m3
        end) as oil_prod_m3_lag_2m,
        max(case
            when production_month = cast(as_of_date - interval '3 months' as date) then oil_prod_m3
        end) as oil_prod_m3_lag_3m,
        avg(case
            when production_month >= cast(as_of_date - interval '3 months' as date) then oil_prod_m3
        end) as oil_prod_m3_roll_mean_3m,
        avg(case
            when production_month >= cast(as_of_date - interval '6 months' as date) then oil_prod_m3
        end) as oil_prod_m3_roll_mean_6m,
        count(*) as months_with_history,
        min(production_month) as first_observed_month,
        max(production_month) as last_observed_month
    from known
    group by well_id, as_of_date

),

static_attributes as (

    select
        well_id,
        basin,
        field,
        resource_type
    from {{ ref("dim_well") }}

)

select
    {{ dbt_utils.generate_surrogate_key(["aggregated.well_id", "aggregated.as_of_date"]) }} as feature_key,
    aggregated.well_id,
    aggregated.as_of_date,
    aggregated.oil_prod_m3_lag_1m,
    aggregated.oil_prod_m3_lag_2m,
    aggregated.oil_prod_m3_lag_3m,
    aggregated.oil_prod_m3_roll_mean_3m,
    aggregated.oil_prod_m3_roll_mean_6m,
    aggregated.months_with_history,
    cast(
        extract(year from age(aggregated.as_of_date, aggregated.first_observed_month)) * 12
        + extract(month from age(aggregated.as_of_date, aggregated.first_observed_month))
        as integer
    ) as well_age_months,
    aggregated.last_observed_month,
    static_attributes.basin,
    static_attributes.field,
    static_attributes.resource_type
from aggregated
left join static_attributes on aggregated.well_id = static_attributes.well_id
