import httpx

from app.cache import cache_get, cache_set
from app.config import settings


def get_mandi_prices(commodity: str, state: str, district: str) -> dict:
    cache_key = f"mandi:{commodity}:{state}:{district}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = httpx.get(
            "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070",
            params={
                "api-key": settings.data_gov_api_key,
                "format": "json",
                "limit": 5,
                "filters[commodity]": commodity,
                "filters[state.keyword]": state,   # API requires state.keyword for filtering
                "filters[district]": district,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        records = data.get("records", [])
        if not records:
            return {"error": "No records found"}

        rec = records[0]
        result = {
            "commodity": rec.get("commodity", commodity),
            "market": rec.get("market"),
            "state": rec.get("state", state),
            "price": rec.get("modal_price"),
            "min_price": rec.get("min_price"),
            "max_price": rec.get("max_price"),
            "unit": "INR/Quintal",
            "date": rec.get("arrival_date"),
        }
        cache_set(cache_key, result, ttl_seconds=1800)
        return result
    except Exception as e:
        return {"error": str(e)}
