from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from src.core.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", scheme_name="ApiKeyAuth", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> None:
    if api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Forbidden")
