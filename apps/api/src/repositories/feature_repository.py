"""Feature-store repository — reads persisted contract-A features (F3-18).

Reads one feature vector from ``features.well_features`` keyed by
``(well_id, as_of_date)`` — the point-in-time projection ML consumers rely on
(ADR-0031). Returns an empty frame when the row is absent (unknown well, or a
cutoff that was never materialized), which the service turns into a clear 404.
"""

from datetime import date
from typing import Any

import pandas as pd
import psycopg
from petrocast_ml.features import CONTRACT_COLUMNS, CONTRACT_SCHEMA, FeatureKind
from psycopg.rows import dict_row

# Columns come from the frozen feature contract (constants), never user input.
_QUERY = (
    f"SELECT {', '.join(CONTRACT_COLUMNS)} "  # noqa: S608
    "FROM features.well_features "
    "WHERE well_id = %s AND as_of_date = %s"
)


def read(conn: psycopg.Connection[Any], *, well_id: str, as_of_date: date) -> pd.DataFrame:
    """Return the persisted feature row for *(well_id, as_of_date)*, or empty.

    The frame carries exactly ``CONTRACT_COLUMNS`` in canonical order, dtypes
    coerced to the contract families (numeric → float, date → datetime, text →
    object) so the model signature consumes it unchanged.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(_QUERY, (well_id, as_of_date))
        rows = cur.fetchall()

    frame = pd.DataFrame(rows, columns=list(CONTRACT_COLUMNS))
    return _coerce_dtypes(frame)


def _coerce_dtypes(frame: pd.DataFrame) -> pd.DataFrame:
    for column, kind in CONTRACT_SCHEMA.items():
        if kind is FeatureKind.NUMERIC:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")
        elif kind is FeatureKind.DATE:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
        else:
            frame[column] = frame[column].astype("object")
    return frame
