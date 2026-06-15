{{
    config(
        materialized="incremental",
        incremental_strategy="delete+insert",
        unique_key="well_key",
        schema="gold",
        tags=["gold"],
    )
}}

-- Silver -> Gold: well dimension (SCD Type 1, one row per well).
-- The surrogate key `well_key` is a deterministic hash of the business key
-- `well_id`; delete+insert upserts by that key (SCD1 overwrite, no duplicates).
-- The well universe is the union of wells appearing in the registry
-- (silver_wells) and in production (silver_production), so every fact well has a
-- dimension row (no FK gaps). Registry attributes win over production-derived
-- ones for shared fields; formation/resource_type come from production only.

with well_ids as (

    select well_id from {{ ref("silver_wells") }}
    union
    select well_id from {{ ref("silver_production") }}

),

registry as (

    select
        well_id,
        well_alias,
        field,
        basin,
        province,
        depth_m,
        latitude,
        longitude,
        classification,
        sub_classification,
        reservoir_type
    from {{ ref("silver_wells") }}

),

production_ranked as (

    select
        production.well_id,
        production.well_alias,
        production.field,
        production.basin,
        production.province,
        production.formation,
        production.resource_type,
        row_number() over (
            partition by production.well_id
            order by production.production_month desc
        ) as row_num
    from {{ ref("silver_production") }} as production

),

production_attributes as (

    select
        well_id,
        well_alias,
        field,
        basin,
        province,
        formation,
        resource_type
    from production_ranked
    where row_num = 1

)

select
    {{ dbt_utils.generate_surrogate_key(["well_ids.well_id"]) }} as well_key,
    well_ids.well_id,
    coalesce(registry.well_alias, production_attributes.well_alias) as well_alias,
    coalesce(registry.field, production_attributes.field) as field,
    coalesce(registry.basin, production_attributes.basin) as basin,
    coalesce(registry.province, production_attributes.province) as province,
    registry.depth_m,
    registry.latitude,
    registry.longitude,
    registry.classification,
    registry.sub_classification,
    registry.reservoir_type,
    production_attributes.formation,
    production_attributes.resource_type
from well_ids
left join registry on well_ids.well_id = registry.well_id
left join production_attributes on well_ids.well_id = production_attributes.well_id
