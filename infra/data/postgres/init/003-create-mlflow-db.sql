-- Local fallback backend store for MLflow (ADR-0032, backlog F3-08).
--
-- The team backend is a shared cloud Postgres (see
-- docs/runbooks/mlflow-tracking.md); this database exists so the tracking
-- stack can also run fully offline (local demo / smoke) against the
-- data-stack Postgres. Runs at first boot of the data_postgres volume, after
-- 001/002 (lexicographic order). For volumes initialized before this file
-- existed, create it manually: `CREATE DATABASE mlflow;`.
CREATE DATABASE mlflow;
