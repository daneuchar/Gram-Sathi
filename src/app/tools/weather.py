import httpx

from app.cache import cache_get, cache_set

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_WMO_CONDITIONS = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Cloudy",
    45: "Foggy", 48: "Icy fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow",
    80: "Light showers", 81: "Showers", 82: "Heavy showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


def _wmo_condition(code: int) -> str:
    return _WMO_CONDITIONS.get(code, "Unknown")


def get_weather_forecast(district: str, state: str) -> dict:
    cache_key = f"weather:{district}:{state}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        geo = httpx.get(
            _GEOCODE_URL,
            params={"name": district, "count": 1, "language": "en", "format": "json", "countryCode": "IN"},
            timeout=10,
        )
        geo.raise_for_status()
        results = geo.json().get("results", [])
        if not results:
            return {"error": f"Location not found: {district}, {state}"}

        lat = results[0]["latitude"]
        lon = results[0]["longitude"]

        fc = httpx.get(
            _FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
                "timezone": "Asia/Kolkata",
                "forecast_days": 5,
            },
            timeout=10,
        )
        fc.raise_for_status()
        daily = fc.json()["daily"]

        days_with_temp = []   # today + tomorrow (full detail)
        days_outlook = []     # days 3-5 (condition + rain only, no temp)
        alerts = []

        for i, date in enumerate(daily["time"]):
            max_temp = daily["temperature_2m_max"][i]
            min_temp = daily["temperature_2m_min"][i]
            rain_mm = daily["precipitation_sum"][i] or 0.0
            condition = _wmo_condition(daily["weathercode"][i] or 0)

            if rain_mm > 50:
                alerts.append(f"Heavy rain alert ({rain_mm}mm) on {date}")
            if max_temp is not None and max_temp > 45:
                alerts.append(f"Heatwave alert ({max_temp}°C) on {date}")
            if min_temp is not None and min_temp < 4:
                alerts.append(f"Frost alert ({min_temp}°C) on {date}")

            if i < 2:
                days_with_temp.append({
                    "date": date,
                    "max_temp_c": max_temp,
                    "min_temp_c": min_temp,
                    "rain_mm": rain_mm,
                    "condition": condition,
                })
            else:
                days_outlook.append({
                    "date": date,
                    "condition": condition,
                    "rain_mm": rain_mm,
                })

        result = {
            "district": district,
            "state": state,
            "next_2_days": days_with_temp,
            "outlook_days_3_to_5": days_outlook,
            "alerts": alerts,
            "note": "Temperature details for days 3-5 are available if the farmer explicitly asks.",
        }
        cache_set(cache_key, result, ttl_seconds=7200)
        return result

    except Exception as e:
        return {"error": str(e)}
