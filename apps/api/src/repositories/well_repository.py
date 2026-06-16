"""Well repository — reads from gold.dim_well.

Column mapping:
    gold.dim_well.well_id  →  WellInfo.id_well
"""

from typing import Any

import psycopg
from psycopg.rows import dict_row

from src.schemas.well import WellInfo


def get_all(conn: psycopg.Connection[Any]) -> list[WellInfo]:
    """Return all wells from gold.dim_well."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT well_id FROM gold.dim_well ORDER BY well_id")
        rows = cur.fetchall()
    return [WellInfo(id_well=row["well_id"]) for row in rows]


def exists(conn: psycopg.Connection[Any], well_id: str) -> bool:
    """Return True if *well_id* exists in gold.dim_well."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM gold.dim_well WHERE well_id = %s LIMIT 1",
            (well_id,),
        )
        return cur.fetchone() is not None
