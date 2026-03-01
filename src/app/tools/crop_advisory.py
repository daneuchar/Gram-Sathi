from datetime import datetime

ADVISORIES = {
    ("wheat", "rabi"): {
        "crop": "wheat",
        "season": "rabi",
        "advisory": (
            "Sow improved varieties like HD-2967 or PBW-343. "
            "Apply first irrigation at crown root initiation (21 days). "
            "Use 120 kg N, 60 kg P, 40 kg K per hectare. "
            "Monitor for yellow rust and apply fungicide if needed."
        ),
    },
    ("rice", "kharif"): {
        "crop": "rice",
        "season": "kharif",
        "advisory": (
            "Transplant 25-30 day old seedlings at 20x15 cm spacing. "
            "Maintain 5 cm standing water during tillering. "
            "Apply 120 kg N in 3 splits. "
            "Watch for stem borer and blast disease."
        ),
    },
    ("tomato", "rabi"): {
        "crop": "tomato",
        "season": "rabi",
        "advisory": (
            "Transplant 4-week seedlings at 60x45 cm spacing. "
            "Apply 120 kg N, 80 kg P, 60 kg K per hectare. "
            "Stake plants after 30 days. "
            "Monitor for early blight and fruit borer."
        ),
    },
}

FALLBACK_ADVISORY = "Consult your local KVK or call Kisan Call Centre 1800-180-1551"


def _current_season() -> str:
    month = datetime.now().month
    if 6 <= month <= 9:
        return "kharif"
    elif month >= 10 or month <= 2:
        return "rabi"
    else:
        return "zaid"


def get_crop_advisory(crop: str, state: str) -> dict:
    season = _current_season()
    key = (crop.lower(), season)
    advisory = ADVISORIES.get(key)

    if advisory:
        return {**advisory, "state": state}

    return {
        "crop": crop,
        "season": season,
        "state": state,
        "advisory": FALLBACK_ADVISORY,
    }
