"""Unit tests for the champion serving dependency (F3-18)."""

import pandas as pd
import pytest
from fastapi import HTTPException
from petrocast_ml.inference import ChampionModel

from src.core import serving
from src.core.config import settings


class _StubModel:
    def predict(self, model_input: pd.DataFrame) -> object:
        return model_input


def test_get_champion_returns_loaded_champion(monkeypatch):
    serving._load_cached_champion.cache_clear()
    sentinel = object()
    monkeypatch.setattr(serving, "load_champion", lambda _settings: sentinel)

    assert serving.get_champion() is sentinel

    serving._load_cached_champion.cache_clear()


def test_get_champion_maps_load_failure_to_503(monkeypatch):
    serving._load_cached_champion.cache_clear()

    def boom(_settings):
        raise RuntimeError("registry down")

    monkeypatch.setattr(serving, "load_champion", boom)

    with pytest.raises(HTTPException) as exc_info:
        serving.get_champion()
    assert exc_info.value.status_code == 503
    assert "Model registry is unavailable" in exc_info.value.detail

    serving._load_cached_champion.cache_clear()


def test_champion_health_reports_not_loaded_before_first_use():
    serving._load_cached_champion.cache_clear()

    expected_uri = f"models:/{settings.mlflow_model_name}@{settings.mlflow_model_alias}"
    assert serving.champion_health() == {
        "status": "not_loaded",
        "model_uri": expected_uri,
    }


def test_champion_health_reports_version_once_loaded(monkeypatch):
    serving._load_cached_champion.cache_clear()
    champion = ChampionModel(
        model=_StubModel(),
        version="7",
        uri="models:/petrocast-production/7",
    )
    monkeypatch.setattr(serving, "load_champion", lambda _settings: champion)
    serving.get_champion()

    assert serving.champion_health() == {
        "status": "loaded",
        "model_uri": "models:/petrocast-production/7",
        "model_version": "7",
    }

    serving._load_cached_champion.cache_clear()
