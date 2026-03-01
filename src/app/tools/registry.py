from app.tools.mandi import get_mandi_prices
from app.tools.weather import get_weather_forecast
from app.tools.schemes import check_scheme_eligibility
from app.tools.crop_advisory import get_crop_advisory

NOVA_TOOLS = [
    {
        "toolSpec": {
            "name": "get_mandi_prices",
            "description": "Get current mandi (agricultural market) prices for a commodity in a given state and district.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "commodity": {"type": "string", "description": "Crop or commodity name, e.g. Wheat, Rice, Tomato"},
                        "state": {"type": "string", "description": "Indian state name, e.g. Madhya Pradesh"},
                        "district": {"type": "string", "description": "District name, e.g. Sehore"},
                    },
                    "required": ["commodity", "state", "district"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_weather_forecast",
            "description": "Get a 5-day weather forecast for a district and state in India, including alerts for heavy rain, heatwave, or frost.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "district": {"type": "string", "description": "District name"},
                        "state": {"type": "string", "description": "State name"},
                    },
                    "required": ["district", "state"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "check_scheme_eligibility",
            "description": "Check government scheme eligibility for a farmer based on their profile (land holding, state, crop, category).",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "land_holding": {"type": "number", "description": "Land holding in acres"},
                        "state": {"type": "string", "description": "State name"},
                        "crop": {"type": "string", "description": "Primary crop"},
                        "category": {"type": "string", "description": "Farmer category (small/marginal/large)"},
                    },
                    "required": [],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_crop_advisory",
            "description": "Get season-aware crop advisory for a given crop and state in India.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "crop": {"type": "string", "description": "Crop name, e.g. wheat, rice, tomato"},
                        "state": {"type": "string", "description": "State name"},
                    },
                    "required": ["crop", "state"],
                }
            },
        }
    },
]

_TOOL_DISPATCH = {
    "get_mandi_prices": lambda inp: get_mandi_prices(inp["commodity"], inp["state"], inp["district"]),
    "get_weather_forecast": lambda inp: get_weather_forecast(inp["district"], inp["state"]),
    "check_scheme_eligibility": lambda inp: check_scheme_eligibility(inp),
    "get_crop_advisory": lambda inp: get_crop_advisory(inp["crop"], inp["state"]),
}


def execute_tool(tool_name: str, tool_input: dict) -> dict:
    handler = _TOOL_DISPATCH.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}
    return handler(tool_input)
