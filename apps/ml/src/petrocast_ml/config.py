from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ML_APP_DIR = Path(__file__).resolve().parents[2]


class MlSettings(BaseSettings):
    """ML configuration loaded from environment variables or `apps/ml/.env`."""

    model_config = SettingsConfigDict(
        env_file=ML_APP_DIR / ".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=False,
    )

    mlflow_tracking_uri: str = "http://localhost:5000"
    mlflow_experiment_name: str = "petrocast-production-forecast"
    mlflow_artifact_root: str = Field(
        default="./mlartifacts",
        validation_alias=AliasChoices(
            "PETROCAST_MLFLOW_ARTIFACT_ROOT",
            "mlflow_artifact_root",
        ),
    )
    mlflow_model_name: str = Field(
        default="petrocast-production",
        validation_alias=AliasChoices(
            "PETROCAST_MLFLOW_MODEL_NAME",
            "mlflow_model_name",
        ),
    )
    mlflow_model_alias: str = Field(
        default="champion",
        validation_alias=AliasChoices(
            "PETROCAST_MLFLOW_MODEL_ALIAS",
            "mlflow_model_alias",
        ),
    )

    @property
    def champion_model_uri(self) -> str:
        return f"models:/{self.mlflow_model_name}@{self.mlflow_model_alias}"


@lru_cache
def get_settings() -> MlSettings:
    return MlSettings()
