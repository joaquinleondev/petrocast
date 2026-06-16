from typing import Any

import psycopg

from src.repositories import well_repository
from src.schemas.well import WellInfo


def get_all_wells(conn: psycopg.Connection[Any]) -> list[WellInfo]:
    return well_repository.get_all(conn)
