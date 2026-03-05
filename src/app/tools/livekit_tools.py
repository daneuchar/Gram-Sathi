"""LiveKit-compatible tool definitions wrapping existing tool functions."""
from __future__ import annotations

import asyncio

from livekit.agents.llm import function_tool

from app.tools.weather import get_weather_forecast as _get_weather
from app.tools.mandi import get_mandi_prices as _get_mandi
from app.tools.crop_advisory import get_crop_advisory as _get_advisory
from app.tools.schemes import check_scheme_eligibility as _check_schemes


@function_tool(description="Get a 5-day weather forecast for any district and state in India, including alerts for heavy rain, heatwave, or frost. You MUST call this tool for ANY weather question. NEVER guess weather information.")
async def get_weather_forecast(district: str, state: str) -> dict:
    return await asyncio.to_thread(_get_weather, district, state)


@function_tool(
    description=(
        "Get current mandi (agricultural market) prices for a commodity in ANY state in India. "
        "The farmer can ask about prices in any state, not just their home state. "
        "For example, a farmer from Tamil Nadu can ask about tomato prices in Haryana. "
        "State is required. District is optional — if unknown, omit it. "
        "You MUST call this tool for ANY question about crop prices. NEVER answer price questions from memory."
    )
)
async def get_mandi_prices(commodity: str, state: str, district: str = "") -> dict:
    return await asyncio.to_thread(_get_mandi, commodity, state, district or None)


@function_tool(description="Get season-aware crop advisory for a given crop and state in India.")
async def get_crop_advisory(crop: str, state: str) -> dict:
    return await asyncio.to_thread(_get_advisory, crop, state)


@function_tool(description="Check government scheme eligibility for a farmer based on their profile.")
async def check_scheme_eligibility(land_holding: float = 0, state: str = "", crop: str = "", category: str = "") -> dict:
    profile = {}
    if land_holding:
        profile["land_holding"] = land_holding
    if state:
        profile["state"] = state
    if crop:
        profile["crop"] = crop
    if category:
        profile["category"] = category
    return await asyncio.to_thread(_check_schemes, profile)


ALL_TOOLS = [get_weather_forecast, get_mandi_prices, get_crop_advisory, check_scheme_eligibility]
