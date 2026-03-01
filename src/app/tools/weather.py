import httpx

from app.cache import cache_get, cache_set
from app.config import settings


def get_weather_forecast(district: str, state: str) -> dict:
    cache_key = f"weather:{district}:{state}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = httpx.get(
            "https://api.indianapi.in/weather",
            params={"location": f"{district}, {state}", "days": 5},
            headers={"X-Api-Key": settings.indian_api_key},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        forecast = []
        alerts = []

        for day in data.get("forecast", []):
            entry = {
                "date": day.get("date"),
                "max_temp": day.get("max_temp"),
                "min_temp": day.get("min_temp"),
                "condition": day.get("condition"),
                "rain_mm": day.get("rain_mm", 0),
            }
            forecast.append(entry)

            rain_mm = float(entry["rain_mm"] or 0)
            max_temp = float(entry["max_temp"] or 0)
            min_temp = float(entry["min_temp"] or 0)

            if rain_mm > 50:
                alerts.append(f"Heavy rain alert ({rain_mm}mm) on {entry['date']}")
            if max_temp > 45:
                alerts.append(f"Heatwave alert ({max_temp}°C) on {entry['date']}")
            if min_temp < 4:
                alerts.append(f"Frost alert ({min_temp}°C) on {entry['date']}")

        result = {
            "district": district,
            "state": state,
            "forecast": forecast,
            "alerts": alerts,
        }
        cache_set(cache_key, result, ttl_seconds=7200)
        return result
    except Exception as e:
        return {"error": str(e)}
