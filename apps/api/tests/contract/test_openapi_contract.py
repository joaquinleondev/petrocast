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


def test_prediction_contract_is_frozen():
    """Contrato D (ADR-0034 / F3-17): request/response of /api/v1/predictions.

    Consumed by F3-18/F3-20/F3-21/F3-23. Changing any of these fields means
    breaking the frozen handoff contract: revisit ADR-0034 and notify the
    consumers before touching this test.
    """
    spec = app.openapi()
    operation = spec["paths"]["/api/v1/predictions"]["get"]

    params = {p["name"]: p for p in operation["parameters"]}
    assert set(params) == {"id_well", "as_of_date", "horizon"}
    assert all(p["required"] for p in params.values())
    assert params["as_of_date"]["schema"]["format"] == "date"
    assert params["horizon"]["schema"]["minimum"] == 1
    assert params["horizon"]["schema"]["maximum"] == 12

    assert {"403", "404", "422", "503"} <= set(operation["responses"])

    response_ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    response = spec["components"]["schemas"][response_ref.rsplit("/", 1)[-1]]
    assert set(response["required"]) == {
        "id_well",
        "as_of_date",
        "horizon",
        "model_version",
        "predictions",
    }

    point_ref = response["properties"]["predictions"]["items"]["$ref"]
    point = spec["components"]["schemas"][point_ref.rsplit("/", 1)[-1]]
    assert set(point["required"]) == {"month", "oil_prod_m3"}
