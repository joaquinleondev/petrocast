import os

import httpx
import pytest

BASE_URL = os.getenv("SMOKE_BASE_URL")
API_KEY = os.getenv("SMOKE_API_KEY", "abcdef12345")

pytestmark = pytest.mark.skipif(
    BASE_URL is None, reason="SMOKE_BASE_URL not set (run post-deploy)"
)


def test_live():
    r = httpx.get(f"{BASE_URL}/health/live", timeout=5)
    assert r.status_code == 200


def test_ready():
    r = httpx.get(f"{BASE_URL}/health/ready", timeout=5)
    assert r.status_code == 200


def test_deep_requires_key():
    r = httpx.get(f"{BASE_URL}/health/deep", timeout=5)
    assert r.status_code == 403


def test_wells():
    r = httpx.get(
        f"{BASE_URL}/api/v1/wells",
        params={"date_query": "2024-01-01"},
        headers={"X-API-Key": API_KEY},
        timeout=5,
    )
    assert r.status_code == 200


def test_forecast():
    r = httpx.get(
        f"{BASE_URL}/api/v1/forecast",
        params={
            "id_well": "POZO-001",
            "date_start": "2024-01-01",
            "date_end": "2024-01-05",
        },
        headers={"X-API-Key": API_KEY},
        timeout=5,
    )
    assert r.status_code == 200
