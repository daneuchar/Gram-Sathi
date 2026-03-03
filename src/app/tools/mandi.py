import httpx
from datetime import datetime, timedelta

from app.cache import cache_get, cache_set
from app.config import settings

# Primary: today's live feed (sparse, mostly North India)
_API_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
# Fallback: broader historical dataset with Tamil Nadu & more states (capitalized fields)
_FALLBACK_API_URL = "https://api.data.gov.in/resource/35985678-0d79-46b4-9ed6-6f13308a1d24"


def _parse_date(raw: str | None) -> str | None:
    """Convert DD/MM/YYYY (data.gov.in) to '2 March 2026' to avoid LLM misreading."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%d/%m/%Y").strftime("%-d %B %Y")
    except ValueError:
        return raw


def _fetch(url: str, params: dict) -> list[dict]:
    resp = httpx.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("records", [])


def _normalize(rec: dict) -> dict:
    """Normalize capitalized field names from the fallback API to lowercase."""
    if "State" in rec:
        return {k.lower(): v for k, v in rec.items()}
    return rec


def _records_to_result(records: list[dict], commodity: str, state: str) -> dict:
    if not records:
        return {"error": f"No mandi price data found for {commodity} in {state}"}
    results = []
    for rec in records[:5]:
        rec = _normalize(rec)
        results.append({
            "commodity": rec.get("commodity", commodity),
            "market": rec.get("market"),
            "district": rec.get("district"),
            "state": rec.get("state", state),
            "modal_price": rec.get("modal_price"),
            "min_price": rec.get("min_price"),
            "max_price": rec.get("max_price"),
            "unit": "INR/Quintal",
            "date": _parse_date(rec.get("arrival_date")),
        })
    return {"prices": results}


def get_mandi_prices(commodity: str, state: str, district: str | None = None) -> dict:
    cache_key = f"mandi:{commodity}:{state}:{district or 'all'}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    api_key = settings.data_gov_api_key

    try:
        # --- Primary API (lowercase field filters) ---
        base_params = {
            "api-key": api_key,
            "format": "json",
            "limit": 5,
            "filters[commodity]": commodity,
            "filters[state.keyword]": state,
        }

        # 1. Try district filter first
        if district:
            records = _fetch(_API_URL, {**base_params, "filters[district]": district})
        else:
            records = []

        # 2. Fall back to state-level within primary
        if not records:
            records = _fetch(_API_URL, base_params)

        # --- Fallback API: rolling 3-day window, today → yesterday → -2 → -3 ---
        if not records:
            fb_base = {
                "api-key": api_key,
                "format": "json",
                "limit": 5,
                "filters[Commodity]": commodity,
                "filters[State]": state,
            }
            today = datetime.now()
            for days_back in range(4):  # 0=today, 1=yesterday, 2, 3
                date_str = (today - timedelta(days=days_back)).strftime("%d/%m/%Y")
                fb_dated = {**fb_base, "filters[Arrival_Date]": date_str}
                if district:
                    records = _fetch(_FALLBACK_API_URL, {**fb_dated, "filters[District]": district})
                if not records:
                    records = _fetch(_FALLBACK_API_URL, fb_dated)
                if records:
                    break

        result = _records_to_result(records, commodity, state)
        cache_set(cache_key, result, ttl_seconds=1800)
        return result

    except Exception as e:
        return {"error": str(e)}
