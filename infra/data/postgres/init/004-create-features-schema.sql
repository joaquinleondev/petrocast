-- Feature store schema (ADR-0031, F3-09). Separate from gold: gold is the
-- BI/API consumption layer; `features` is an ML contract with its own rules
-- (point-in-time correctness, per-cutoff versioning). Tables are managed by
-- dbt (apps/data/dbt/models/features/).
create schema if not exists features;
