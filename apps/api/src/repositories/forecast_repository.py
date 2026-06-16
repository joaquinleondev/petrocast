"""Forecast repository — reads production actuals from gold.fact_production.

Mapping strategy:
    The gold schema stores monthly production actuals. This repository returns
    those actuals directly as ``ForecastRow`` records — each row becomes one
    ``ForecastPoint`` with:
        date  = gold.fact_production.production_month (ISO string YYYY-MM-DD)
        prod  = gold.fact_production.oil_prod_m3 (float)

    Rows are filtered to the requested [date_start, date_end] window (inclusive)
    and ordered chronologically. An empty result (unknown well or no data in the
    requested window) signals to the service layer that the well was not found.

    The returned rows are sorted by date ascending; whether they are declining
    depends on the real data in the gold layer.
"""

from datetime import date
from typing import Any

import psycopg
from psycopg.rows import dict_row

ForecastRow = dict[str, str | float]


def generate(
    conn: psycopg.Connection[Any],
    id_well: str,
    date_start: date,
    date_end: date,
) -> list[ForecastRow]:
    """Return production actuals for *id_well* in [date_start, date_end].

    Returns an empty list when the well does not exist or has no production
    data in the requested window.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
                production_month::date AS production_month,
                COALESCE(oil_prod_m3, 0.0) AS oil_prod_m3
            FROM gold.fact_production
            WHERE well_id = %s
              AND production_month >= %s
              AND production_month <= %s
            ORDER BY production_month ASC
            """,
            (id_well, date_start, date_end),
        )
        rows = cur.fetchall()

    return [
        {
            "date": row["production_month"].isoformat()
            if hasattr(row["production_month"], "isoformat")
            else str(row["production_month"]),
            "prod": float(row["oil_prod_m3"]),
        }
        for row in rows
    ]
