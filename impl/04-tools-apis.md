# Task 04: Tools & External APIs

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Implement the 4 Nova tool functions: Mandi prices, Weather forecast, Government scheme eligibility, Crop advisory.

**Branch:** `feat/tools`
**Worktree:** `../gramvaani-tools`
**Depends On:** Task 01 (backend-foundation merged)

**Architecture:** Each tool is a standalone async function with Redis caching. Tools are registered as Nova tool definitions (Bedrock `toolConfig` format). The pipeline's `tool_executor` dispatches by tool name.

---

## Setup

```bash
git checkout feat/backend-foundation
git pull
git checkout -b feat/tools
mkdir -p app/tools tests/tools
touch app/tools/__init__.py tests/tools/__init__.py
```

---

### Step 1: Write failing tests for all tools

**Create `tests/tools/test_mandi.py`:**

```python
import pytest
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
async def test_get_mandi_prices_returns_price():
    from app.tools.mandi import get_mandi_prices
    mock_data = {"records": [{"modal_price": "2340", "commodity": "Wheat", "market": "Jaipur"}]}
    with patch("app.tools.mandi._fetch_from_api", new_callable=AsyncMock, return_value=mock_data):
        result = await get_mandi_prices("Wheat", "Rajasthan", "Jaipur")
    assert result["commodity"] == "Wheat"
    assert "price" in result

@pytest.mark.asyncio
async def test_mandi_prices_cached():
    from app.tools.mandi import get_mandi_prices
    from app.redis_client import cache_set
    import json
    cached = {"commodity": "Rice", "price": "1800", "market": "Chennai", "unit": "quintal"}
    await cache_set("mandi:Rice:Tamil Nadu:Chennai", json.dumps(cached), 1800)
    result = await get_mandi_prices("Rice", "Tamil Nadu", "Chennai")
    assert result["price"] == "1800"
```

**Create `tests/tools/test_weather.py`:**

```python
import pytest
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
async def test_get_weather_returns_forecast():
    from app.tools.weather import get_weather_forecast
    mock_data = {"forecast": [{"date": "2026-03-01", "temp_max": 32, "rainfall_mm": 0}]}
    with patch("app.tools.weather._fetch_weather_api", new_callable=AsyncMock, return_value=mock_data):
        result = await get_weather_forecast("Jaipur", "Rajasthan")
    assert "forecast" in result
    assert len(result["forecast"]) > 0
```

**Run:** `pytest tests/tools/ -v`
Expected: FAIL — modules not found.

---

### Step 2: Mandi prices tool

**Create `app/tools/mandi.py`:**

```python
import httpx
import json
from app.config import settings
from app.redis_client import cache_get, cache_set

CACHE_TTL = 1800  # 30 minutes

async def _fetch_from_api(commodity: str, state: str, district: str) -> dict:
    """Fetch from data.gov.in OGD platform."""
    url = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
    params = {
        "api-key": settings.data_gov_api_key,
        "format": "json",
        "limit": 5,
        "filters[commodity]": commodity,
        "filters[state]": state,
        "filters[district]": district,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        return resp.json()

async def get_mandi_prices(commodity: str, state: str, district: str) -> dict:
    """
    Tool: get_mandi_prices
    Returns current mandi prices for a commodity in a district.
    Cached for 30 minutes.
    """
    cache_key = f"mandi:{commodity}:{state}:{district}"
    cached = await cache_get(cache_key)
    if cached:
        return json.loads(cached)

    try:
        data = await _fetch_from_api(commodity, state, district)
        records = data.get("records", [])
        if not records:
            return {"error": f"No price data found for {commodity} in {district}, {state}"}

        record = records[0]
        result = {
            "commodity": record.get("commodity", commodity),
            "market": record.get("market", district),
            "state": state,
            "price": record.get("modal_price", "N/A"),
            "min_price": record.get("min_price", "N/A"),
            "max_price": record.get("max_price", "N/A"),
            "unit": "quintal",
            "date": record.get("arrival_date", "today"),
        }
        await cache_set(cache_key, json.dumps(result), CACHE_TTL)
        return result

    except Exception as e:
        return {"error": f"Could not fetch mandi prices: {str(e)}"}
```

---

### Step 3: Weather forecast tool

**Create `app/tools/weather.py`:**

```python
import httpx
import json
from app.config import settings
from app.redis_client import cache_get, cache_set

CACHE_TTL = 7200  # 2 hours
ALERT_THRESHOLDS = {"heavy_rain_mm": 50, "heatwave_celsius": 45, "frost_celsius": 4}

async def _fetch_weather_api(district: str, state: str) -> dict:
    url = f"https://api.indianapi.in/weather"
    params = {"location": f"{district}, {state}", "days": 5}
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            params=params,
            headers={"X-Api-Key": settings.indian_api_key},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()

async def get_weather_forecast(district: str, state: str) -> dict:
    """
    Tool: get_weather_forecast
    Returns 5-day weather forecast with farming alerts.
    Cached for 2 hours.
    """
    cache_key = f"weather:{district}:{state}"
    cached = await cache_get(cache_key)
    if cached:
        return json.loads(cached)

    try:
        data = await _fetch_weather_api(district, state)
        forecast = []
        alerts = []

        for day in data.get("forecast", [])[:5]:
            entry = {
                "date": day.get("date"),
                "temp_max_c": day.get("maxtemp_c"),
                "temp_min_c": day.get("mintemp_c"),
                "rainfall_mm": day.get("totalprecip_mm", 0),
                "humidity_pct": day.get("avghumidity"),
                "condition": day.get("condition", {}).get("text", ""),
            }
            forecast.append(entry)

            # Generate alerts
            if entry["rainfall_mm"] >= ALERT_THRESHOLDS["heavy_rain_mm"]:
                alerts.append(f"Heavy rain expected on {entry['date']} — {entry['rainfall_mm']}mm")
            if entry["temp_max_c"] and entry["temp_max_c"] >= ALERT_THRESHOLDS["heatwave_celsius"]:
                alerts.append(f"Heatwave warning on {entry['date']} — {entry['temp_max_c']}°C")
            if entry["temp_min_c"] and entry["temp_min_c"] <= ALERT_THRESHOLDS["frost_celsius"]:
                alerts.append(f"Frost risk on {entry['date']} — {entry['temp_min_c']}°C")

        result = {"district": district, "state": state, "forecast": forecast, "alerts": alerts}
        await cache_set(cache_key, json.dumps(result), CACHE_TTL)
        return result

    except Exception as e:
        return {"error": f"Could not fetch weather: {str(e)}"}
```

---

### Step 4: Scheme eligibility tool (Amazon Q Business)

**Create `app/tools/schemes.py`:**

```python
import boto3
from app.config import settings

def check_scheme_eligibility(farmer_profile: dict) -> dict:
    """
    Tool: check_scheme_eligibility
    Queries Amazon Q Business for government schemes matching farmer profile.
    """
    if not settings.amazon_q_app_id:
        return {"error": "Amazon Q Business not configured"}

    client = boto3.client(
        "qbusiness",
        region_name=settings.aws_default_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

    # Build natural language query from farmer profile
    land = farmer_profile.get("land_acres", "small")
    state = farmer_profile.get("state", "India")
    crops = farmer_profile.get("crops", "")
    query = f"Government schemes for {land} acre farmer in {state} growing {crops}"

    try:
        resp = client.chat_sync(
            applicationId=settings.amazon_q_app_id,
            userMessage=query,
        )
        answer = resp.get("systemMessage", "")
        sources = [s.get("title", "") for s in resp.get("sourceAttributions", [])]
        return {"schemes": answer, "sources": sources[:3]}

    except Exception as e:
        return {"error": f"Scheme lookup failed: {str(e)}"}
```

---

### Step 5: Crop advisory tool

**Create `app/tools/crop_advisory.py`:**

```python
import datetime

# Season detection by month
def _get_season() -> str:
    month = datetime.datetime.now().month
    if month in [6, 7, 8, 9]: return "kharif"
    if month in [10, 11, 12, 1, 2]: return "rabi"
    return "zaid"

# Static advisory database (extend with LLM for dynamic advice)
ADVISORIES = {
    ("wheat", "rabi"): {
        "sowing": "Sow in October-November, seed rate 100-125 kg/ha",
        "irrigation": "6 irrigations needed — crown root, tillering, jointing, flowering, grain filling, dough stage",
        "fertilizer": "NPK 120:60:40 kg/ha. Apply urea in splits.",
        "pest": "Watch for yellow rust and aphids. Spray Propiconazole 25EC if needed.",
        "harvest": "Harvest when grain moisture drops to 12-14%",
    },
    ("rice", "kharif"): {
        "sowing": "Transplant 25-30 day old seedlings in June-July",
        "irrigation": "Keep 5cm standing water during vegetative stage",
        "fertilizer": "NPK 120:60:60 kg/ha",
        "pest": "Monitor for brown planthopper. Avoid excess nitrogen.",
        "harvest": "Harvest 30 days after 80% flowering",
    },
    ("tomato", "rabi"): {
        "sowing": "Transplant October-November in raised beds",
        "irrigation": "Drip irrigation, 3-4 liters/plant/day",
        "fertilizer": "High potassium during fruiting stage",
        "pest": "Watch for leaf curl virus — control whitefly vector",
        "harvest": "Harvest at breaker stage for transport, fully red for local market",
    },
}

async def get_crop_advisory(crop: str, state: str) -> dict:
    """
    Tool: get_crop_advisory
    Returns season-aware farming advice for a crop.
    """
    season = _get_season()
    key = (crop.lower(), season)
    advisory = ADVISORIES.get(key)

    if advisory:
        return {"crop": crop, "season": season, "state": state, **advisory}

    # Fallback for unknown crops
    return {
        "crop": crop,
        "season": season,
        "advice": f"For {crop} in {season} season in {state}: consult your local Krishi Vigyan Kendra (KVK) or call Kisan Call Centre at 1800-180-1551.",
    }
```

---

### Step 6: Tool registry & executor

**Create `app/tools/registry.py`:**

```python
from app.tools.mandi import get_mandi_prices
from app.tools.weather import get_weather_forecast
from app.tools.schemes import check_scheme_eligibility
from app.tools.crop_advisory import get_crop_advisory

# Nova tool definitions (Bedrock toolConfig format)
NOVA_TOOLS = [
    {
        "toolSpec": {
            "name": "get_mandi_prices",
            "description": "Get current market prices for agricultural commodities at local mandis",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "commodity": {"type": "string", "description": "Crop name e.g. Wheat, Rice, Tomato"},
                        "state": {"type": "string", "description": "Indian state name"},
                        "district": {"type": "string", "description": "District or city name"},
                    },
                    "required": ["commodity", "state", "district"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_weather_forecast",
            "description": "Get 5-day hyperlocal weather forecast with farming alerts",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "district": {"type": "string"},
                        "state": {"type": "string"},
                    },
                    "required": ["district", "state"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "check_scheme_eligibility",
            "description": "Check government scheme eligibility based on farmer profile",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "land_acres": {"type": "number"},
                        "state": {"type": "string"},
                        "crops": {"type": "string"},
                    },
                    "required": ["state"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_crop_advisory",
            "description": "Get season-aware crop advisory for sowing, irrigation, pest management",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "crop": {"type": "string"},
                        "state": {"type": "string"},
                    },
                    "required": ["crop", "state"],
                }
            },
        }
    },
]

async def execute_tool(tool_name: str, tool_input: dict) -> dict:
    """Dispatch tool call from Nova to the correct function."""
    if tool_name == "get_mandi_prices":
        return await get_mandi_prices(**tool_input)
    elif tool_name == "get_weather_forecast":
        return await get_weather_forecast(**tool_input)
    elif tool_name == "check_scheme_eligibility":
        return check_scheme_eligibility(tool_input)
    elif tool_name == "get_crop_advisory":
        return await get_crop_advisory(**tool_input)
    else:
        return {"error": f"Unknown tool: {tool_name}"}
```

---

### Step 7: Run tests

```bash
pytest tests/tools/ -v
```

Expected: All PASSED (with mocked API calls)

---

### Step 8: Commit

```bash
git add app/tools/ tests/tools/
git commit -m "feat: tools — mandi prices, weather, schemes (Amazon Q), crop advisory + registry"
```

---

## Done when:
- [ ] All 4 tools implemented with Redis caching
- [ ] `NOVA_TOOLS` definitions compatible with Bedrock `toolConfig`
- [ ] `execute_tool()` dispatcher wired
- [ ] Tests pass with mocked external APIs
