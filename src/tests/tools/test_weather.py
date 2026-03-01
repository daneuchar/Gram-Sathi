from unittest.mock import patch, MagicMock

from app.tools.weather import get_weather_forecast


MOCK_WEATHER_RESPONSE = {
    "forecast": [
        {
            "date": "2026-03-01",
            "max_temp": "32",
            "min_temp": "18",
            "condition": "Sunny",
            "rain_mm": 0,
        },
        {
            "date": "2026-03-02",
            "max_temp": "30",
            "min_temp": "17",
            "condition": "Partly cloudy",
            "rain_mm": 5,
        },
    ]
}

MOCK_HEAVY_RAIN_RESPONSE = {
    "forecast": [
        {
            "date": "2026-03-01",
            "max_temp": "28",
            "min_temp": "20",
            "condition": "Heavy rain",
            "rain_mm": 75,
        },
    ]
}


@patch("app.tools.weather.httpx.get")
def test_get_weather_returns_forecast(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_WEATHER_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    result = get_weather_forecast("Sehore", "Madhya Pradesh")

    assert len(result["forecast"]) > 0
    assert result["district"] == "Sehore"
    assert result["state"] == "Madhya Pradesh"


@patch("app.tools.weather.httpx.get")
def test_weather_generates_heavy_rain_alert(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_HEAVY_RAIN_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    result = get_weather_forecast("Indore", "Madhya Pradesh")

    assert len(result["alerts"]) > 0
    assert any("Heavy rain" in a for a in result["alerts"])
