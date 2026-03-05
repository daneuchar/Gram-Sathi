# Government Scheme Eligibility Tool — Design

## Problem
The current `check_scheme_eligibility` tool depends on Amazon Q Business which is not configured. Farmers asking about government schemes get an error. No free public API exists for Indian government scheme data.

## Approach
Curate a JSON file of ~50-70 farmer schemes (central + top state schemes) and filter at runtime based on farmer profile. The LLM then summarizes the most relevant matches in the farmer's language.

## Data: `src/app/assets/schemes.json`

~20 central schemes + 2-3 top schemes per major agricultural state (~15 states).

### Schema per entry:
```json
{
  "id": "pm-kisan",
  "name": "PM-KISAN Samman Nidhi",
  "name_hi": "पीएम-किसान सम्मान निधि",
  "type": "central",
  "states": ["all"],
  "description": "Direct income support of Rs 6000/year in 3 installments to farmer families",
  "eligibility": {
    "land_holding_max_acres": null,
    "categories": ["small", "marginal", "large"],
    "crops": []
  },
  "benefits": "Rs 6000 per year in 3 equal installments of Rs 2000",
  "how_to_apply": "Register through local CSC or pmkisan.gov.in with Aadhaar and bank details",
  "documents": ["Aadhaar card", "Bank account", "Land records"]
}
```

### Fields:
- `id`: unique slug
- `name` / `name_hi`: English + Hindi name
- `type`: "central" or "state"
- `states`: `["all"]` for central, `["Telangana", "Andhra Pradesh"]` for state-specific
- `eligibility.land_holding_max_acres`: null = no limit, number = max acres
- `eligibility.categories`: which farmer categories qualify (small/marginal/large)
- `eligibility.crops`: empty = all crops, otherwise specific crops
- `benefits`: what the farmer gets
- `how_to_apply`: steps to apply
- `documents`: required documents

## Logic: `src/app/tools/schemes.py`

1. Load `schemes.json` once at module import time
2. Auto-classify farmer category from land holding:
   - <= 2.5 acres → "marginal"
   - <= 5 acres → "small"
   - > 5 acres → "large"
3. Filter schemes by:
   - State: match "all" (central) or farmer's state
   - Category: farmer's category must be in scheme's categories list
   - Crop: if farmer specifies a crop and scheme has crop restrictions, match
4. Return top 5 matching schemes as list of dicts (name, benefits, how_to_apply, documents)

## Tool signature (unchanged):
```python
def check_scheme_eligibility(farmer_profile: dict) -> dict
```
Input: `{"state": "Telangana", "crop": "rice", "land_holding": 3, "category": ""}`
Output: `{"schemes": [...], "total_matched": 12}`

## Integration
- No changes needed to `livekit_agent.py` — tool signature stays the same
- Remove Amazon Q Business / boto3 dependency from schemes.py
- No external API calls, works offline, instant response

## Schemes to include

### Central (all-India):
1. PM-KISAN Samman Nidhi
2. PM Fasal Bima Yojana (PMFBY)
3. Kisan Credit Card (KCC)
4. Soil Health Card Scheme
5. PM Krishi Sinchai Yojana (irrigation)
6. National Mission on Sustainable Agriculture
7. Paramparagat Krishi Vikas Yojana (organic farming)
8. e-NAM (electronic market)
9. National Food Security Mission
10. Rashtriya Krishi Vikas Yojana
11. Sub-Mission on Agricultural Mechanization
12. PM Kisan Maandhan Yojana (pension)
13. Agriculture Infrastructure Fund
14. Micro Irrigation Fund
15. National Beekeeping & Honey Mission

### State schemes (2-3 per state):
- Telangana: Rythu Bandhu, Rythu Bima
- Andhra Pradesh: YSR Rythu Bharosa, YSR Free Crop Insurance
- Tamil Nadu: TN Crop Insurance, Free Borewell Scheme
- Karnataka: Raitha Siri, Krishi Bhagya
- Maharashtra: Namo Shetkari Mahasanman Nidhi
- Madhya Pradesh: CM Kisan Kalyan Yojana
- Uttar Pradesh: PM Kisan Samman Nidhi top-up
- Punjab: Debt Waiver Scheme
- Haryana: Bhavantar Bharpayee Yojana
- Rajasthan: Mukhya Mantri Krishak Sathi Yojana
- Gujarat: Kisan Suryodaya Yojana
- West Bengal: Krishak Bandhu
- Bihar: Bihar Rajya Fasal Sahayata Yojana
- Odisha: KALIA Scheme
- Kerala: Vegetable Development Programme
