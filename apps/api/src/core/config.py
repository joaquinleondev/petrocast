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


settings = Settings()
