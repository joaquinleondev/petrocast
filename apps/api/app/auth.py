import os

from dotenv import load_dotenv
from fastapi import Header, HTTPException

load_dotenv()

_API_KEY = os.getenv("API_KEY", "abcdef12345")


def verify_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if x_api_key != _API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
