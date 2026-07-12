{{
    config(
        materialized="incremental",
        incremental_strategy="delete+insert",
        unique_key="production_month",
        schema="silver",
        tags=["silver"],
        on_schema_change="append_new_columns",
    )
}}

-- Bronze -> Silver: typed, normalized, English-named monthly production by well.
-- Idempotency lives here: `delete+insert` keyed on `production_month` rebuilds a
-- whole month on rerun. The month is derived from the data (`anio`/`mes`), not
-- from the Bronze snapshot partition tag. `min_month`/`max_month` vars scope a
-- backfill range; the partitioned Dagster asset passes them per partition.

with source as (

    select *
    from {{ source("bronze", "production_by_well") }}
    where
        nullif(trim(anio), '') is not null
        and nullif(trim(mes), '') is not null

),

renamed as (

    select
        cast(idpozo as text) as well_id,
        cast(idempresa as text) as company_id,
        -- Negative production is not a real measurement: the source publishes a
        -- handful of negative months (rectificaciones de DDJJ — 3 rows in 410k
        -- as of 2026-05). Treat them as unknown, same as the blanks above,
        -- instead of clamping to 0 (which would assert the well produced
        -- nothing). Keeps the accepted_range checks blocking (F2-18).
        {{ non_negative("prod_pet") }} as oil_prod_m3,
        {{ non_negative("prod_gas") }} as gas_prod_mm3,
        {{ non_negative("prod_agua") }} as water_prod_m3,
        cast(_dlt_load_id as text) as dlt_load_id,
        nullif(trim(empresa), '') as company_name,
        nullif(trim(sigla), '') as well_alias,
        make_date(cast(anio as integer), cast(mes as integer), 1) as production_month,
        nullif(trim(tipo_de_recurso), '') as resource_type,
        nullif(trim(formacion), '') as formation,
        nullif(trim(areayacimiento), '') as field,
        nullif(trim(cuenca), '') as basin,
        nullif(trim(provincia), '') as province
    from source

),

deduplicated as (

    select
        renamed.*,
        row_number() over (
            partition by renamed.well_id, renamed.production_month
            order by renamed.dlt_load_id desc
        ) as row_num
    from renamed

)

select
    well_id,
    company_id,
    company_name,
    well_alias,
    production_month,
    oil_prod_m3,
    gas_prod_mm3,
    water_prod_m3,
    resource_type,
    formation,
    field,
    basin,
    province,
    dlt_load_id
from deduplicated
where
    row_num = 1
    {% if var("min_month", none) is not none %}
        and production_month >= cast('{{ var("min_month") }}' as date)
        and production_month < cast('{{ var("max_month") }}' as date)
    {% endif %}
