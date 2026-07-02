-- Singular test (F3-11): point-in-time / anti-leakage guarantee of contract A.
-- Recomputes every feature of features.well_features straight from gold using
-- ONLY production months strictly before each cutoff present in the table, and
-- returns any row where the persisted value diverges. If the model ever leaked
-- data at or after as_of_date (e.g. a dropped where-clause), the persisted
-- features would differ from this restricted recomputation wherever future
-- months exist — exactly the failure this test surfaces. Also fails if a well
-- with pre-cutoff history is missing from the store (completeness).

{% set lag_columns = {
    "oil_prod_m3_lag_1m": 1,
    "oil_prod_m3_lag_2m": 2,
    "oil_prod_m3_lag_3m": 3,
    "oil_prod_m3_lag_6m": 6,
    "oil_prod_m3_lag_12m": 12,
} %}
{% set window_columns = {
    "oil_prod_m3_roll_mean_3m": ("avg", 3),
    "oil_prod_m3_roll_mean_6m": ("avg", 6),
    "oil_prod_m3_roll_mean_12m": ("avg", 12),
    "oil_prod_m3_roll_std_6m": ("stddev", 6),
    "oil_prod_m3_roll_std_12m": ("stddev", 12),
} %}
{% set float_columns = (lag_columns | list) + (window_columns | list)
    + ["oil_prod_m3_trend_6m", "oil_prod_m3_trend_12m"] %}
{% set exact_columns = [
    "months_with_history",
    "well_age_months",
    "months_since_last_observed",
    "zero_months_12m",
    "last_observed_month",
] %}

with features as (

    select * from {{ ref("well_features") }}

),

cutoffs as (

    select distinct as_of_date from features

),

known as (

    select
        fact_production.well_id,
        cutoffs.as_of_date,
        fact_production.production_month,
        fact_production.oil_prod_m3,
        cast(
            extract(year from fact_production.production_month) * 12
            + extract(month from fact_production.production_month)
            as double precision
        ) as month_index
    from {{ ref("fact_production") }} as fact_production
    cross join cutoffs
    where fact_production.production_month < cutoffs.as_of_date

),

recomputed as (

    select
        well_id,
        as_of_date,
        {% for column, months in lag_columns.items() %}
            max(case
                when production_month = cast(as_of_date - interval '{{ months }} month' as date)
                    then oil_prod_m3
            end) as {{ column }},
        {% endfor %}
        {% for column, (func, months) in window_columns.items() %}
            {{ func }}(case
                when production_month >= cast(as_of_date - interval '{{ months }} month' as date)
                    then oil_prod_m3
            end) as {{ column }},
        {% endfor %}
        regr_slope(
            case
                when production_month >= cast(as_of_date - interval '6 months' as date)
                    then oil_prod_m3
            end,
            month_index
        ) as oil_prod_m3_trend_6m,
        regr_slope(
            case
                when production_month >= cast(as_of_date - interval '12 months' as date)
                    then oil_prod_m3
            end,
            month_index
        ) as oil_prod_m3_trend_12m,
        count(*) filter (
            where
            oil_prod_m3 = 0
            and production_month >= cast(as_of_date - interval '12 months' as date)
        ) as zero_months_12m,
        count(*) as months_with_history,
        cast(
            extract(year from age(as_of_date, min(production_month))) * 12
            + extract(month from age(as_of_date, min(production_month)))
            as integer
        ) as well_age_months,
        cast(
            extract(year from age(as_of_date, max(production_month))) * 12
            + extract(month from age(as_of_date, max(production_month)))
            as integer
        ) as months_since_last_observed,
        max(production_month) as last_observed_month
    from known
    group by well_id, as_of_date

)

select
    coalesce(features.well_id, recomputed.well_id) as well_id,
    coalesce(features.as_of_date, recomputed.as_of_date) as as_of_date,
    features.well_id is null as missing_in_store,
    recomputed.well_id is null as missing_in_recompute
from features
full outer join recomputed
    on
        features.well_id = recomputed.well_id
        and features.as_of_date = recomputed.as_of_date
where
    features.well_id is null
    or recomputed.well_id is null
    {% for column in float_columns %}
        or (features.{{ column }} is null) != (recomputed.{{ column }} is null)
        or abs(features.{{ column }} - recomputed.{{ column }}) > 1e-6
    {% endfor %}
    {% for column in exact_columns %}
        or features.{{ column }} is distinct from recomputed.{{ column }}
    {% endfor %}
