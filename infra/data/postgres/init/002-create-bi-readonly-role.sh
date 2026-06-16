#!/bin/sh
# 002-create-bi-readonly-role.sh
# Creates the read-only BI role "petrocast_bi" scoped to the gold schema only.
# Runs automatically on first postgres volume initialisation (docker-entrypoint-initdb.d).
#
# Requirements:
#   PETROCAST_BI_DB_PASSWORD  — password for the petrocast_bi login role (required)
#   POSTGRES_USER             — set by the postgres image (the superuser / dbt user)
#   POSTGRES_DB               — set by the postgres image
set -eu

# The BI role is optional: if no password is provided, skip creation so the core
# data stack still initialises (the role is only needed for Metabase, F2-20).
if [ -z "${PETROCAST_BI_DB_PASSWORD:-}" ]; then
    echo "[002] PETROCAST_BI_DB_PASSWORD not set — skipping read-only BI role creation."
    exit 0
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create the read-only BI login role (idempotent: DO block guards the CREATE).
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'petrocast_bi') THEN
            CREATE ROLE petrocast_bi LOGIN PASSWORD '${PETROCAST_BI_DB_PASSWORD}';
        END IF;
    END
    \$\$;

    -- Explicit safety: ensure petrocast_bi has NO access to bronze or silver.
    REVOKE ALL PRIVILEGES ON SCHEMA bronze FROM petrocast_bi;
    REVOKE ALL PRIVILEGES ON SCHEMA silver FROM petrocast_bi;

    -- Grant read access to the gold schema (current tables).
    GRANT USAGE ON SCHEMA gold TO petrocast_bi;
    GRANT SELECT ON ALL TABLES IN SCHEMA gold TO petrocast_bi;

    -- Ensure future tables created by the dbt user (POSTGRES_USER) in gold
    -- are automatically readable by petrocast_bi.
    ALTER DEFAULT PRIVILEGES FOR ROLE "${POSTGRES_USER}" IN SCHEMA gold
        GRANT SELECT ON TABLES TO petrocast_bi;
EOSQL

echo "[002] petrocast_bi role created/verified with read-only access to gold schema."
