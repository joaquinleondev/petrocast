"""Database connection dependency for FastAPI.

Yields a psycopg 3 connection per request, built from settings.
Tests override this dependency via ``app.dependency_overrides`` to inject a
fake connection without needing a live Postgres instance.

Usage in an endpoint::

    @router.get("/example")
    def endpoint(conn: DBConn) -> ...:
        ...
"""

from collections.abc import Generator
from typing import Annotated, Any

import psycopg
from fastapi import Depends, HTTPException

from src.core.config import settings

# Type alias re-exported so endpoints/repos can reference it without
# importing psycopg directly.
type Connection = psycopg.Connection[Any]


def get_connection() -> Generator[Connection, None, None]:
    """FastAPI dependency: open a psycopg 3 connection, yield it, then close.

    Raises HTTP 503 if the data-warehouse is unreachable so callers get a
    sensible error rather than an unhandled exception.
    """
    dsn = (
        f"host={settings.dw_host} "
        f"port={settings.dw_port} "
        f"dbname={settings.dw_database} "
        f"user={settings.dw_user} "
        f"password={settings.dw_password}"
    )
    try:
        conn = psycopg.connect(dsn)
    except psycopg.OperationalError as exc:
        raise HTTPException(
            status_code=503,
            detail="Data warehouse is unavailable. Try again later.",
        ) from exc

    try:
        yield conn
    finally:
        conn.close()


# Convenience type for annotated injection
DBConn = Annotated[Connection, Depends(get_connection)]
