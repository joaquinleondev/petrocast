import pytest
from hypothesis import HealthCheck, settings

schemathesis = pytest.importorskip("schemathesis")

from src.main import app  # noqa: E402

schema = schemathesis.openapi.from_asgi("/openapi.json", app)


@schema.parametrize()
@settings(
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.too_slow],
)
def test_api_conforms_to_openapi(case):
    case.call_and_validate(
        headers={"X-API-Key": "abcdef12345"},
        excluded_checks=[
            schemathesis.checks.positive_data_acceptance,
        ],
    )
