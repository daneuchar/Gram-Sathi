# src/tests/tools/test_weather.py
import pytest
from unittest.mock import patch, MagicMock
from app.tools.weather import get_weather_forecast, _wmo_condition


def test_wmo_condition_clear():
    assert _wmo_condition(0) == "Clear sky"


def test_wmo_condition_rain():
    assert _wmo_condition(63) == "Moderate rain"


def test_wmo_condition_unknown():
    assert _wmo_condition(999) == "Unknown"


def test_get_weather_forecast_success():
    geocode_resp = MagicMock()
    geocode_resp.raise_for_status = MagicMock()
    geocode_resp.json.return_value = {
        "results": [{"latitude": 13.08, "longitude": 80.27, "name": "Chennai"}]
    }

    forecast_resp = MagicMock()
    forecast_resp.raise_for_status = MagicMock()
    forecast_resp.json.return_value = {
        "daily": {
            "time": ["2026-03-03"],
            "temperature_2m_max": [33.0],
            "temperature_2m_min": [22.0],
            "precipitation_sum": [0.0],
            "weathercode": [1],
        }
    }

    with patch("app.tools.weather.cache_get", return_value=None), \
         patch("app.tools.weather.cache_set"), \
         patch("httpx.get", side_effect=[geocode_resp, forecast_resp]):
        result = get_weather_forecast("Chennai", "Tamil Nadu")

    assert "forecast" in result
    assert result["forecast"][0]["max_temp"] == 33.0
    assert result["forecast"][0]["condition"] == "Mainly clear"
    assert result["alerts"] == []


def test_get_weather_forecast_heavy_rain_alert():
    geocode_resp = MagicMock()
    geocode_resp.raise_for_status = MagicMock()
    geocode_resp.json.return_value = {
        "results": [{"latitude": 13.08, "longitude": 80.27, "name": "Chennai"}]
    }

    forecast_resp = MagicMock()
    forecast_resp.raise_for_status = MagicMock()
    forecast_resp.json.return_value = {
        "daily": {
            "time": ["2026-03-03"],
            "temperature_2m_max": [28.0],
            "temperature_2m_min": [22.0],
            "precipitation_sum": [75.0],
            "weathercode": [65],
        }
    }

    with patch("app.tools.weather.cache_get", return_value=None), \
         patch("app.tools.weather.cache_set"), \
         patch("httpx.get", side_effect=[geocode_resp, forecast_resp]):
        result = get_weather_forecast("Chennai", "Tamil Nadu")

    assert any("Heavy rain" in a for a in result["alerts"])


def test_get_weather_forecast_no_geocode_result():
    geocode_resp = MagicMock()
    geocode_resp.raise_for_status = MagicMock()
    geocode_resp.json.return_value = {"results": []}

    with patch("app.tools.weather.cache_get", return_value=None), \
         patch("httpx.get", return_value=geocode_resp):
        result = get_weather_forecast("Nowhere", "Nowhere State")

    assert "error" in result
