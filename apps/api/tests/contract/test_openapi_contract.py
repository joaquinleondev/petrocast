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
            # The API now declares ApiKeyAuth (F2-01), so Schemathesis runs its
            # ignored_auth check. That check only accepts HTTP 401 as a valid
            # "auth required" response, but the contract (ADR-0007) mandates 403
            # for a missing/invalid key, so it reports a false positive here.
            schemathesis.checks.ignored_auth,
        ],
    )
