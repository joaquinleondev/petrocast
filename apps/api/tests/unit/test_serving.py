"""Unit tests for the champion serving dependency (F3-18)."""

import pytest
from fastapi import HTTPException

from src.core import serving


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
