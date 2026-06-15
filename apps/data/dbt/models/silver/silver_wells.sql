{{
    config(
        materialized="table",
        schema="silver",
        tags=["silver"],
    )
}}

-- Bronze -> Silver: complementary wells registry, normalized to the current
-- snapshot (one row per well). Per ADR-0026 this source has no monthly grain, so
-- it is materialized as a full-refresh table rather than partitioned.

with source as (

    select *
    from {{ source("bronze", "wells_registry") }}
    where nullif(trim(idpozo), '') is not null

),

renamed as (

    select
        cast(idpozo as text) as well_id,
        cast(idempresa as text) as company_id,
        cast(nullif(trim(profundidad), '') as numeric) as depth_m,
        cast(nullif(trim(coordenaday), '') as double precision) as latitude,
        cast(nullif(trim(coordenadax), '') as double precision) as longitude,
        cast(_dlt_load_id as text) as dlt_load_id,
        nullif(trim(sigla), '') as well_alias,
        nullif(trim(formprod), '') as production_formation,
        nullif(trim(areayacimiento), '') as field,
        nullif(trim(cuenca), '') as basin,
        nullif(trim(provincia), '') as province,
        nullif(trim(clasificacion), '') as classification,
        nullif(trim(subclasificacion), '') as sub_classification,
        nullif(trim(tipo_reservorio), '') as reservoir_type
    from source

),

deduplicated as (

    select
        renamed.*,
        row_number() over (
            partition by renamed.well_id
            order by renamed.dlt_load_id desc
        ) as row_num
    from renamed

)

select
    well_id,
    well_alias,
    company_id,
    production_formation,
    field,
    basin,
    province,
    depth_m,
    latitude,
    longitude,
    classification,
    sub_classification,
    reservoir_type,
    dlt_load_id
from deduplicated
where row_num = 1
