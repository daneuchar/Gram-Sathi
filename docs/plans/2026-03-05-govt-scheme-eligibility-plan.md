# Government Scheme Eligibility Tool — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the broken Amazon Q Business scheme tool with a curated JSON dataset of ~50 central + state farmer schemes, filtered by state/crop/land-holding at runtime.

**Architecture:** A `schemes.json` file ships with the app in `src/app/assets/`. On import, `schemes.py` loads it into memory. The `check_scheme_eligibility()` function filters by state, auto-classifies farmer category from land holding, and returns top 5 matches. No external API calls.

**Tech Stack:** Python, JSON file, pytest

---

### Task 1: Create the schemes JSON data file

**Files:**
- Create: `src/app/assets/schemes.json`

**Step 1: Create the JSON file with central schemes**

Create `src/app/assets/schemes.json` with the following structure. Include these ~15 central schemes and ~30 state schemes (2-3 per state for 15 major agricultural states).

Each entry follows this schema:
```json
{
  "id": "pm-kisan",
  "name": "PM-KISAN Samman Nidhi",
  "type": "central",
  "states": ["all"],
  "description": "Direct income support of Rs 6000 per year to farmer families in 3 installments",
  "eligibility": {
    "land_holding_max_acres": null,
    "categories": ["small", "marginal", "large"],
    "crops": []
  },
  "benefits": "Rs 6000 per year in 3 equal installments of Rs 2000 each, directly to bank account",
  "how_to_apply": "Register at pmkisan.gov.in or visit nearest CSC center with Aadhaar and bank details",
  "documents": ["Aadhaar card", "Bank account passbook", "Land ownership records"]
}
```

**Central schemes to include (type=central, states=["all"]):**

1. **pm-kisan** — PM-KISAN Samman Nidhi: Rs 6000/year income support. All farmers. Apply at pmkisan.gov.in.
2. **pmfby** — PM Fasal Bima Yojana: Crop insurance at 2% premium for kharif, 1.5% for rabi. All farmers. Apply through bank or CSC.
3. **kcc** — Kisan Credit Card: Short-term crop loans at 4% interest (with subvention). All farmers. Apply at any bank.
4. **soil-health-card** — Soil Health Card Scheme: Free soil testing and nutrient recommendations. All farmers. Apply at local agriculture office.
5. **pmksy** — PM Krishi Sinchai Yojana: Subsidy on micro-irrigation (drip/sprinkler) up to 55%. All farmers. Apply at agriculture dept.
6. **pkvy** — Paramparagat Krishi Vikas Yojana: Rs 50000/ha over 3 years for organic farming. Small/marginal. Apply through farmer groups.
7. **enam** — e-NAM: Online mandi trading platform, better prices, transparent auctions. All farmers. Register at enam.gov.in.
8. **nfsm** — National Food Security Mission: Subsidized seeds, demonstrations, training for rice/wheat/pulses/coarse cereals. All farmers. Apply at district agriculture office.
9. **rkvy** — Rashtriya Krishi Vikas Yojana: Infrastructure grants for agriculture projects. All farmers through state govt. Apply via state agriculture dept.
10. **smam** — Sub-Mission on Agricultural Mechanization: 50-80% subsidy on farm equipment for SC/ST/small/marginal farmers. Apply at agrimachinery.nic.in.
11. **pm-kisan-maandhan** — PM Kisan Maandhan Yojana: Monthly pension of Rs 3000 after age 60 for small/marginal farmers. Contribution Rs 55-200/month. Apply at CSC.
12. **aif** — Agriculture Infrastructure Fund: Interest subvention of 3% on loans up to Rs 2 crore for post-harvest infra. All farmers. Apply through bank.
13. **micro-irrigation-fund** — Micro Irrigation Fund: State-level support for drip/sprinkler irrigation expansion. All farmers. Apply via state dept.
14. **nbhm** — National Beekeeping & Honey Mission: Subsidy on bee colonies, equipment, training. All farmers. Apply at nbhm.gov.in.
15. **nmsa** — National Mission on Sustainable Agriculture: Training and support for climate-resilient farming. All farmers. Apply at agriculture office.

**State schemes to include (type=state, states=[specific state]):**

- **Telangana**: rythu-bandhu (Rs 10000/acre/year), rythu-bima (Rs 5 lakh life insurance)
- **Andhra Pradesh**: ysr-rythu-bharosa (Rs 13500/year), ysr-free-crop-insurance
- **Tamil Nadu**: tn-free-borewell (free borewells for small farmers), tn-crop-insurance
- **Karnataka**: raitha-siri (organic farming support), krishi-bhagya (farm ponds subsidy)
- **Maharashtra**: namo-shetkari (Rs 6000/year state top-up), maharashtra-crop-insurance
- **Madhya Pradesh**: cm-kisan-kalyan (Rs 4000/year state top-up), mp-bhavantar
- **Uttar Pradesh**: up-kisan-samman (state top-up), up-free-borewell
- **Punjab**: punjab-crop-diversification, punjab-tubewell-subsidy
- **Haryana**: bhavantar-bharpayee (price deficiency payment), haryana-solar-pump
- **Rajasthan**: mukhya-mantri-krishak-sathi (Rs 2 lakh accident insurance), rajasthan-micro-irrigation
- **Gujarat**: kisan-suryodaya (solar-powered irrigation), gujarat-crop-insurance
- **West Bengal**: krishak-bandhu (Rs 10000/year), krishak-bandhu-death-benefit
- **Bihar**: bihar-fasal-sahayata (crop damage compensation), bihar-diesel-subsidy
- **Odisha**: kalia (Rs 12500/year for small/marginal), kalia-life-insurance
- **Kerala**: kerala-vegetable-development, kerala-coconut-insurance

Use accurate data. For each scheme, verify: eligibility.land_holding_max_acres (null if no limit), eligibility.categories (which of small/marginal/large qualify), eligibility.crops (empty array if all crops).

**Step 2: Validate JSON syntax**

Run: `PYTHONPATH=src uv run python -c "import json; data = json.load(open('src/app/assets/schemes.json')); print(f'Loaded {len(data)} schemes')"`
Expected: `Loaded NN schemes` (should be ~45-50)

**Step 3: Commit**

```bash
git add src/app/assets/schemes.json
git commit -m "data: add curated government scheme dataset (central + state)"
```

---

### Task 2: Write tests for scheme filtering logic

**Files:**
- Create: `src/tests/tools/test_schemes.py`

**Step 1: Write tests**

Create `src/tests/tools/test_schemes.py`:

```python
"""Tests for government scheme eligibility tool."""
import pytest
from app.tools.schemes import check_scheme_eligibility, _classify_farmer


class TestClassifyFarmer:
    def test_marginal_farmer(self):
        assert _classify_farmer(1.5) == "marginal"

    def test_small_farmer(self):
        assert _classify_farmer(4.0) == "small"

    def test_large_farmer(self):
        assert _classify_farmer(10.0) == "large"

    def test_zero_land(self):
        assert _classify_farmer(0) == "marginal"

    def test_boundary_marginal(self):
        assert _classify_farmer(2.5) == "marginal"

    def test_boundary_small(self):
        assert _classify_farmer(5.0) == "small"


class TestCheckSchemeEligibility:
    def test_returns_schemes_for_state(self):
        result = check_scheme_eligibility({"state": "Telangana"})
        assert "schemes" in result
        assert len(result["schemes"]) > 0
        # Should include central schemes + Telangana state schemes
        names = [s["name"] for s in result["schemes"]]
        assert any("PM-KISAN" in n for n in names)

    def test_returns_state_specific_schemes(self):
        result = check_scheme_eligibility({"state": "Telangana"})
        names = [s["name"] for s in result["schemes"]]
        assert any("Rythu Bandhu" in n for n in names)

    def test_excludes_other_state_schemes(self):
        result = check_scheme_eligibility({"state": "Telangana"})
        names = [s["name"] for s in result["schemes"]]
        assert not any("KALIA" in n for n in names)  # Odisha scheme

    def test_filters_by_land_holding(self):
        # Large farmer (10 acres) should not get marginal-only schemes
        result = check_scheme_eligibility({"state": "Odisha", "land_holding": 10})
        names = [s["name"] for s in result["schemes"]]
        # KALIA is for small/marginal only
        assert not any("KALIA" in n.upper() for n in names)

    def test_no_state_returns_central_only(self):
        result = check_scheme_eligibility({})
        assert "schemes" in result
        # Should only return central schemes
        for s in result["schemes"]:
            assert s.get("type") == "central"

    def test_limits_to_five_results(self):
        result = check_scheme_eligibility({"state": "Telangana"})
        assert len(result["schemes"]) <= 5

    def test_total_matched_count(self):
        result = check_scheme_eligibility({"state": "Telangana"})
        assert "total_matched" in result
        assert result["total_matched"] >= len(result["schemes"])

    def test_scheme_has_required_fields(self):
        result = check_scheme_eligibility({"state": "Telangana"})
        for scheme in result["schemes"]:
            assert "name" in scheme
            assert "benefits" in scheme
            assert "how_to_apply" in scheme
```

**Step 2: Run tests — they should fail**

Run: `PYTHONPATH=src uv run pytest src/tests/tools/test_schemes.py -v`
Expected: FAIL (ImportError for `_classify_farmer`, wrong return format from current implementation)

**Step 3: Commit**

```bash
git add src/tests/tools/test_schemes.py
git commit -m "test: add scheme eligibility tests"
```

---

### Task 3: Implement the scheme filtering logic

**Files:**
- Modify: `src/app/tools/schemes.py` (replace entire file)

**Step 1: Rewrite schemes.py**

Replace the entire contents of `src/app/tools/schemes.py` with:

```python
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
    """Filter schemes by farmer profile and return top 5 matches.

    Args:
        farmer_profile: dict with optional keys: state, crop, land_holding, category

    Returns:
        dict with "schemes" (list of top 5 matches) and "total_matched" count
    """
    schemes = _load_schemes()
    state = farmer_profile.get("state", "")
    crop = farmer_profile.get("crop", "")
    land_holding = farmer_profile.get("land_holding", 0)
    category = farmer_profile.get("category", "") or _classify_farmer(land_holding)

    matched = []
    for s in schemes:
        # State filter: "all" matches everyone, otherwise must match
        s_states = s.get("states", [])
        if "all" not in s_states and state and state not in s_states:
            continue

        # If no state given, only return central schemes
        if not state and "all" not in s_states:
            continue

        # Category filter
        elig = s.get("eligibility", {})
        allowed_cats = elig.get("categories", [])
        if allowed_cats and category and category not in allowed_cats:
            continue

        # Crop filter (only if scheme restricts crops AND farmer specified one)
        scheme_crops = elig.get("crops", [])
        if scheme_crops and crop and crop.lower() not in [c.lower() for c in scheme_crops]:
            continue

        # Land holding max filter
        max_acres = elig.get("land_holding_max_acres")
        if max_acres is not None and land_holding > max_acres:
            continue

        matched.append(s)

    # Return top 5, prioritize state-specific schemes first, then central
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
```

**Step 2: Run tests**

Run: `PYTHONPATH=src uv run pytest src/tests/tools/test_schemes.py -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add src/app/tools/schemes.py
git commit -m "feat: implement scheme eligibility with curated JSON dataset"
```

---

### Task 4: Remove Amazon Q dependency from config

**Files:**
- Modify: `src/app/config.py` (no changes needed — amazon_q_app_id can stay as unused config)

No code change needed. The new `schemes.py` no longer imports boto3 or references `settings`. The `amazon_q_app_id` config field can remain for future use.

**Step 1: Run full test suite to verify nothing broke**

Run: `PYTHONPATH=src uv run pytest src/tests/ -v --tb=short`
Expected: All tests pass

**Step 2: Commit if any cleanup was needed**

---

### Task 5: Verify end-to-end via API

**Step 1: Test the tool directly**

Run:
```bash
PYTHONPATH=src uv run python -c "
from app.tools.schemes import check_scheme_eligibility
result = check_scheme_eligibility({'state': 'Telangana', 'land_holding': 3})
for s in result['schemes']:
    print(f\"- {s['name']}: {s['benefits'][:80]}\")
print(f\"Total matched: {result['total_matched']}\")
"
```
Expected: List of ~5 schemes including PM-KISAN and Rythu Bandhu

**Step 2: Test with different states**

Run:
```bash
PYTHONPATH=src uv run python -c "
from app.tools.schemes import check_scheme_eligibility
for state in ['Tamil Nadu', 'Maharashtra', 'Bihar']:
    result = check_scheme_eligibility({'state': state})
    names = [s['name'] for s in result['schemes']]
    print(f'{state}: {names}')
"
```
Expected: Each state shows central + its own state schemes

**Step 3: Commit all remaining changes and push**

```bash
git add -A
git commit -m "feat: complete government scheme eligibility tool with curated dataset"
git push
```
