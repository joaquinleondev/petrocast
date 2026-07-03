from dagster import MaterializeResult, MetadataValue, asset
from psycopg import sql
from psycopg.connection import Connection

from petrocast_data.settings import get_settings

WAREHOUSE_SCHEMAS = ("bronze", "silver", "gold", "features")


@asset(group_name="warehouse")
def warehouse_schemas_ready() -> MaterializeResult[None]:
    """Ensure the PostgreSQL warehouse exposes the medallion + features schemas."""
    settings = get_settings()
    with (
        Connection.connect(settings.psycopg_dsn, autocommit=True) as connection,
        connection.cursor() as cursor,
    ):
        for schema_name in WAREHOUSE_SCHEMAS:
            cursor.execute(
                sql.SQL("create schema if not exists {}").format(sql.Identifier(schema_name))
            )

    return MaterializeResult(metadata={"schemas": MetadataValue.json(list(WAREHOUSE_SCHEMAS))})
