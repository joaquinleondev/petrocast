from src.main import app

spec = app.openapi()

PROTECTED_OPERATIONS = [
    ("/api/v1/wells", "get"),
    ("/api/v1/forecast", "get"),
    ("/health/deep", "get"),
]


def test_security_scheme_apikeyauth_is_declared() -> None:
    schemes = spec["components"]["securitySchemes"]
    assert "ApiKeyAuth" in schemes

    scheme = schemes["ApiKeyAuth"]
    assert scheme["type"] == "apiKey"
    assert scheme["in"] == "header"
    assert scheme["name"] == "X-API-Key"


def test_protected_operations_require_apikeyauth() -> None:
    for path, method in PROTECTED_OPERATIONS:
        operation = spec["paths"][path][method]
        security = operation.get("security")
        assert security, f"{method.upper()} {path} is missing a security requirement"
        matches = any("ApiKeyAuth" in requirement for requirement in security)
        assert matches, f"{method.upper()} {path} does not reference ApiKeyAuth"


def test_public_operation_does_not_require_auth() -> None:
    operation = spec["paths"]["/health/live"]["get"]
    assert not operation.get("security")
