import pytest
from fastapi.testclient import TestClient

from src.main import app

VALID_KEY = "abcdef12345"


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": VALID_KEY}
