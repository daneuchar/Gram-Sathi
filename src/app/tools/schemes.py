"""Government scheme eligibility tool — curated JSON dataset, filtered at runtime."""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMES_PATH = Path(__file__).resolve().parent.parent / "assets" / "schemes.json"
_SCHEMES: list[dict] = []


def _load_schemes() -> list[dict]:
    global _SCHEMES
    if _SCHEMES:
        return _SCHEMES
    try:
        _SCHEMES = json.loads(_SCHEMES_PATH.read_text(encoding="utf-8"))
        logger.info("Loaded %d government schemes from %s", len(_SCHEMES), _SCHEMES_PATH)
    except Exception:
        logger.exception("Failed to load schemes.json")
        _SCHEMES = []
    return _SCHEMES


def _classify_farmer(land_holding: float) -> str:
    """Classify farmer category based on land holding in acres."""
    if land_holding <= 2.5:
        return "marginal"
    elif land_holding <= 5.0:
        return "small"
    return "large"


def check_scheme_eligibility(farmer_profile: dict) -> dict:
    """Filter schemes by farmer profile and return top 5 matches."""
    schemes = _load_schemes()
    state = farmer_profile.get("state", "")
    crop = farmer_profile.get("crop", "")
    land_holding = farmer_profile.get("land_holding", 0)
    category = farmer_profile.get("category", "") or _classify_farmer(land_holding)

    matched = []
    for s in schemes:
        s_states = s.get("states", [])
        if "all" not in s_states and state and state not in s_states:
            continue
        if not state and "all" not in s_states:
            continue

        elig = s.get("eligibility", {})
        allowed_cats = elig.get("categories", [])
        if allowed_cats and category and category not in allowed_cats:
            continue

        scheme_crops = elig.get("crops", [])
        if scheme_crops and crop and crop.lower() not in [c.lower() for c in scheme_crops]:
            continue

        max_acres = elig.get("land_holding_max_acres")
        if max_acres is not None and land_holding > max_acres:
            continue

        matched.append(s)

    matched.sort(key=lambda s: (0 if s.get("type") == "state" else 1))
    top = matched[:5]

    return {
        "schemes": [
            {
                "name": s["name"],
                "type": s.get("type", "central"),
                "benefits": s.get("benefits", ""),
                "how_to_apply": s.get("how_to_apply", ""),
                "documents": s.get("documents", []),
            }
            for s in top
        ],
        "total_matched": len(matched),
    }
