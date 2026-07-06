from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=False,
    )

    api_key: str = "abcdef12345"

    # Data-warehouse connection — mirrors the PETROCAST_DW_* vars used by the
    # data stack (apps/data). Sane defaults let the app start without a DB.
    dw_host: str = Field(
        default="localhost",
        validation_alias=AliasChoices("PETROCAST_DW_HOST", "dw_host"),
    )
    dw_port: int = Field(
        default=5432,
        validation_alias=AliasChoices("PETROCAST_DW_PORT", "dw_port"),
    )
    dw_user: str = Field(
        default="petrocast",
        validation_alias=AliasChoices("PETROCAST_DW_USER", "dw_user"),
    )
    dw_password: str = Field(
        default="petrocast",
        validation_alias=AliasChoices("PETROCAST_DW_PASSWORD", "dw_password"),
    )
    dw_database: str = Field(
        default="petrocast",
        validation_alias=AliasChoices("PETROCAST_DW_DATABASE", "dw_database"),
    )

    # ML serving (F3-18) — champion model resolved from the MLflow registry.
    # Mirrors the PETROCAST_MLFLOW_* vars used by apps/ml so the API and the
    # training stack point at the same tracking server and champion alias.
    mlflow_tracking_uri: str = Field(
        default="http://localhost:5000",
        validation_alias=AliasChoices("PETROCAST_MLFLOW_TRACKING_URI", "mlflow_tracking_uri"),
    )
    mlflow_model_name: str = Field(
        default="petrocast-production",
        validation_alias=AliasChoices("PETROCAST_MLFLOW_MODEL_NAME", "mlflow_model_name"),
    )
    mlflow_model_alias: str = Field(
        default="champion",
        validation_alias=AliasChoices("PETROCAST_MLFLOW_MODEL_ALIAS", "mlflow_model_alias"),
    )


settings = Settings()
