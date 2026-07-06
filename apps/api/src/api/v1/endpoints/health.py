import os
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from src.api.deps import verify_api_key
from src.core.serving import champion_health

router = APIRouter()

_STARTED_AT = time.monotonic()
_STARTED_AT_ISO = datetime.now(UTC).isoformat()


@router.get("/live")
def health_live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
def health_ready() -> dict[str, Any]:
    return {"status": "ready", "checks": {}}


@router.get(
    "/deep",
    dependencies=[Depends(verify_api_key)],
    responses={403: {"description": "Missing or invalid API key"}},
)
def health_deep() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "petrocast-api",
        "version": os.getenv("BUILD_VERSION", "dev"),
        "commit": os.getenv("BUILD_REVISION", "unknown"),
        "deployed_at": os.getenv("BUILD_CREATED", _STARTED_AT_ISO),
        "uptime_seconds": int(time.monotonic() - _STARTED_AT),
        "checks": {
            "model_serving": champion_health(),
        },
    }
