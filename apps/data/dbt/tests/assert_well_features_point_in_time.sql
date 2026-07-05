{{ config(tags=["features"]) }}

-- PIT guard for the feature store (contract A, ADR-0031 / F3-11): no persisted
-- feature row may see production at or after its own knowledge cutoff. These
-- are data-level invariants that hold for every cutoff ever materialized —
-- unlike a recompute-vs-gold comparison, they stay valid after DDJJ
-- rectifications rewrite gold (snapshots are immutable by design). The
-- definition-level PIT test (recomputing a cutoff with future months removed
-- and asserting nothing changes) lives in apps/ml
-- (tests/unit/test_feature_engineering.py), on the python mirror of this
-- model. Any row returned here is a violation and fails the build.

select
    well_id,
    as_of_date,
    last_observed_month,
    months_since_last_observed,
    months_with_history,
    well_age_months
from {{ ref("well_features") }}
where
    -- the newest month a feature saw must be strictly before the cutoff
    last_observed_month >= as_of_date
    -- staleness derived from it must therefore be at least one month
    or months_since_last_observed < 1
    -- a row only exists for wells with history before the cutoff
    or months_with_history < 1
    -- observed history can never span more months than the well's age
    or months_with_history > well_age_months
