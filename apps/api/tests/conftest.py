"""Shared test fixtures.

DB dependency override
----------------------
All tests run without a live Postgres instance.  We override the
``get_connection`` FastAPI dependency with a fake that returns canned gold-
schema rows.  The override is installed at *session* scope (before the
``TestClient`` is created) so it is active for integration and contract tests.

Canned data
-----------
Wells:  POZO-001, POZO-002, POZO-003
Production: three monthly rows per well (2024-01, 2024-02, 2024-03)
            with declining oil production.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.core.db import get_connection
from src.main import app

VALID_KEY = "abcdef12345"

# ---------------------------------------------------------------------------
# Canned gold data
# ---------------------------------------------------------------------------

_WELLS = [
    {"well_id": "POZO-001"},
    {"well_id": "POZO-002"},
    {"well_id": "POZO-003"},
]

_PRODUCTION: dict[str, list[dict[str, Any]]] = {
    "POZO-001": [
        {"production_month": date(2024, 1, 1), "oil_prod_m3": 150.0},
        {"production_month": date(2024, 2, 1), "oil_prod_m3": 140.0},
        {"production_month": date(2024, 3, 1), "oil_prod_m3": 130.0},
    ],
    "POZO-002": [
        {"production_month": date(2024, 1, 1), "oil_prod_m3": 220.0},
        {"production_month": date(2024, 2, 1), "oil_prod_m3": 210.0},
        {"production_month": date(2024, 3, 1), "oil_prod_m3": 200.0},
    ],
    "POZO-003": [
        {"production_month": date(2024, 1, 1), "oil_prod_m3": 95.0},
        {"production_month": date(2024, 2, 1), "oil_prod_m3": 88.0},
        {"production_month": date(2024, 3, 1), "oil_prod_m3": 81.0},
    ],
}


# ---------------------------------------------------------------------------
# Fake cursor + connection
# ---------------------------------------------------------------------------


class _FakeCursor:
    """Minimal psycopg cursor stub used in tests."""

    def __init__(self) -> None:
        self._rows: list[Any] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        sql_lower = sql.lower()
        if "gold.dim_well" in sql_lower:
            if "where well_id" in sql_lower:
                # exists() check
                well_id = params[0] if params else None
                self._rows = [("1",)] if any(w["well_id"] == well_id for w in _WELLS) else []
            else:
                # get_all()
                self._rows = list(_WELLS)
        elif "gold.fact_production" in sql_lower:
            well_id = params[0] if params else None
            date_start = params[1] if len(params) > 1 else date.min
            date_end = params[2] if len(params) > 2 else date.max
            rows = _PRODUCTION.get(str(well_id), [])
            self._rows = [r for r in rows if date_start <= r["production_month"] <= date_end]
        else:
            self._rows = []

    def fetchall(self) -> list[Any]:
        return list(self._rows)

    def fetchone(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _FakeConnection:
    """Minimal psycopg connection stub used in tests."""

    def cursor(self, *, row_factory: Any = None) -> _FakeCursor:
        return _FakeCursor()

    def close(self) -> None:
        pass


def _fake_get_connection() -> Generator[_FakeConnection, None, None]:
    yield _FakeConnection()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _override_db() -> Generator[None, None, None]:
    """Install fake DB dependency for the whole test session."""
    app.dependency_overrides[get_connection] = _fake_get_connection
    yield
    app.dependency_overrides.pop(get_connection, None)


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": VALID_KEY}


@pytest.fixture
def fake_conn() -> _FakeConnection:
    """Provide a fake connection for unit tests that call repo/service directly."""
    return _FakeConnection()
