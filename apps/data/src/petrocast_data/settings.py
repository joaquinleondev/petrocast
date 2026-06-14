from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DATA_APP_DIR = Path(__file__).resolve().parents[2]


class DataSettings(BaseSettings):
    """Data stack settings, read from env vars or `apps/data/.env` (ADR-0018)."""

    model_config = SettingsConfigDict(
        env_file=DATA_APP_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="PETROCAST_",
        extra="forbid",
        case_sensitive=False,
    )

    dw_host: str = Field(...)
    dw_port: int = 5432
    dw_user: str = Field(...)
    dw_password: SecretStr = Field(...)
    dw_database: str = Field(...)
    source_production_url: str = Field(...)
    source_wells_url: str = Field(...)
    notification_webhook_url: str | None = None

    @property
    def psycopg_dsn(self) -> str:
        password = self.dw_password.get_secret_value()
        return (
            f"host={self.dw_host} "
            f"port={self.dw_port} "
            f"dbname={self.dw_database} "
            f"user={self.dw_user} "
            f"password={password}"
        )

    @property
    def dlt_destination_url(self) -> str:
        password = quote(self.dw_password.get_secret_value(), safe="")
        return (
            f"postgresql://{self.dw_user}:{password}"
            f"@{self.dw_host}:{self.dw_port}/{self.dw_database}"
        )


@lru_cache
def get_settings() -> DataSettings:
    return DataSettings()
