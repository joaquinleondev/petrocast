{{
    config(
        materialized="incremental",
        incremental_strategy="delete+insert",
        unique_key="company_key",
        schema="gold",
        tags=["gold"],
    )
}}

-- Silver -> Gold: company dimension (SCD Type 1, one row per company).
-- The surrogate key `company_key` is a deterministic hash of the business key
-- `company_id`; the delete+insert upsert overwrites the row on reprocess (SCD1)
-- and prevents duplicates. Source: distinct companies in silver_production.

with source as (

    select
        company_id,
        company_name
    from {{ ref("silver_production") }}
    where company_id is not null

),

deduplicated as (

    select
        source.company_id,
        source.company_name,
        row_number() over (
            partition by source.company_id
            order by source.company_name
        ) as row_num
    from source

)

select
    {{ dbt_utils.generate_surrogate_key(["company_id"]) }} as company_key,
    company_id,
    company_name
from deduplicated
where row_num = 1
