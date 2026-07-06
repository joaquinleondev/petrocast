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

    assert set(operation["responses"]) == {"200", "403", "404", "422", "503"}

    for status_code in ("403", "404", "503"):
        error_ref = operation["responses"][status_code]["content"]["application/json"]["schema"][
            "$ref"
        ]
        assert error_ref.endswith("/PredictionError")

    validation_ref = operation["responses"]["422"]["content"]["application/json"]["schema"]["$ref"]
    assert validation_ref.endswith("/PredictionValidationError")

    error = spec["components"]["schemas"]["PredictionError"]
    assert set(error["required"]) == {"detail"}
    assert error["properties"]["detail"]["type"] == "string"

    validation_error = spec["components"]["schemas"]["PredictionValidationError"]
    assert set(validation_error["required"]) == {"detail"}
    assert validation_error["properties"]["detail"]["type"] == "array"
    assert validation_error["properties"]["detail"]["items"]["$ref"].endswith(
        "/PredictionValidationIssue"
    )

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


def test_prediction_openapi_exposes_examples():
    """F3-20: /api/v1/predictions must document realistic examples in OpenAPI.

    Additive-only check (does not touch required/format/minimum/maximum): fails
    if someone strips the `example(s)` added for F3-20 demo/documentation
    purposes (F3-21).
    """
    spec = app.openapi()
    operation = spec["paths"]["/api/v1/predictions"]["get"]

    params = {p["name"]: p for p in operation["parameters"]}
    for name in ("id_well", "as_of_date", "horizon"):
        param = params[name]
        assert (
            "example" in param or "examples" in param
        ), f"query param '{name}' has no OpenAPI example"

    response_ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    response_schema_name = response_ref.rsplit("/", 1)[-1]
    response = spec["components"]["schemas"][response_schema_name]

    # Either a schema-level example/examples, or every property carries its own.
    has_schema_level_example = "example" in response or "examples" in response
    properties = response["properties"]
    has_property_level_examples = all(
        "example" in prop or "examples" in prop for prop in properties.values()
    )
    assert (
        has_schema_level_example or has_property_level_examples
    ), "PredictionResponse schema has no examples (neither schema-level nor per-property)"

    point_ref = response["properties"]["predictions"]["items"]["$ref"]
    point = spec["components"]["schemas"][point_ref.rsplit("/", 1)[-1]]
    for field_name, prop in point["properties"].items():
        assert (
            "example" in prop or "examples" in prop
        ), f"PredictionPoint.{field_name} has no OpenAPI example"
