from fastapi import Header, HTTPException

from src.core.config import settings


def verify_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Forbidden")
