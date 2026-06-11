from pydantic_settings import BaseSettings, SettingsConfigDict


class DataSettings(BaseSettings):
    """Warehouse connection settings, read from `PETROCAST_DW_*` env vars (ADR-0018)."""

    model_config = SettingsConfigDict(env_prefix="PETROCAST_DW_")

    host: str = "localhost"
    port: int = 5432
    user: str = "petrocast"
    password: str = "petrocast"
    database: str = "petrocast"

    @property
    def psycopg_dsn(self) -> str:
        return (
            f"host={self.host} "
            f"port={self.port} "
            f"dbname={self.database} "
            f"user={self.user} "
            f"password={self.password}"
        )

    @property
    def dlt_destination_url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


settings = DataSettings()
