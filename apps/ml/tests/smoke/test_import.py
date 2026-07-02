from datetime import date

import pandas as pd
from pytest import MonkeyPatch

import petrocast_ml
from petrocast_ml import FeatureReader, MlSettings, read_features


class StubFeatureReader:
    def read(self, *, well_id: str, as_of_date: date) -> pd.DataFrame:
        return pd.DataFrame([{"well_id": well_id, "as_of_date": as_of_date, "oil_lag_1": 42.0}])


def test_public_contracts_are_importable() -> None:
    assert petrocast_ml.load_champion
    assert petrocast_ml.predict
    assert petrocast_ml.train
    assert petrocast_ml.create_tracking_client
    assert petrocast_ml.create_registry_client
    assert petrocast_ml.promote_champion


def test_feature_reader_contract_delegates_to_consumer() -> None:
    reader: FeatureReader = StubFeatureReader()

    frame = read_features(reader, well_id="well-1", as_of_date=date(2026, 6, 1))

    assert frame.to_dict(orient="records") == [
        {
            "well_id": "well-1",
            "as_of_date": date(2026, 6, 1),
            "oil_lag_1": 42.0,
        }
    ]


def test_settings_use_contract_c_names(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("mlflow_tracking_uri", "http://mlflow.internal:5000")
    monkeypatch.setenv("MLFLOW_EXPERIMENT_NAME", "smoke-experiment")
    monkeypatch.setenv("PETROCAST_MLFLOW_ARTIFACT_ROOT", "s3://bucket/mlflow")

    settings = MlSettings(_env_file=None)

    assert settings.mlflow_tracking_uri == "http://mlflow.internal:5000"
    assert settings.mlflow_experiment_name == "smoke-experiment"
    assert settings.mlflow_artifact_root == "s3://bucket/mlflow"
    assert settings.champion_model_uri == "models:/petrocast-production@champion"
