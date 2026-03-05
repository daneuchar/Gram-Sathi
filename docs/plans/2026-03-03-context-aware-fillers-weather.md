# Context-Aware Fillers + Open-Meteo Weather Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the broken indianapi.in weather backend with Open-Meteo (free, no key), and add context-aware filler phrase variations for Hindi and Tamil so the voice assistant sounds more natural.

**Architecture:** A keyword classifier on the English transcript picks a filler category (`none`, `generic`, `mandi`, `weather`, `scheme`) before Nova runs. Multiple pre-generated `.raw` audio files per category are loaded at startup and picked randomly each turn. Open-Meteo uses a two-step geocode → forecast flow with no API key.

**Tech Stack:** Python 3.12, httpx (sync for scripts, async in tools), Open-Meteo geocoding + forecast APIs, Sarvam bulbul:v2 TTS, pytest.

---

### Task 1: Rewrite weather tool to use Open-Meteo

**Files:**
- Modify: `src/app/tools/weather.py`
- Create: `src/tests/tools/test_weather.py`

**Step 1: Create the test file**

```python
# src/tests/tools/test_weather.py
import pytest
from unittest.mock import patch, MagicMock
from app.tools.weather import get_weather_forecast, _wmo_condition


def test_wmo_condition_clear():
    assert _wmo_condition(0) == "Clear sky"


def test_wmo_condition_rain():
    assert _wmo_condition(63) == "Moderate rain"


def test_wmo_condition_unknown():
    assert _wmo_condition(999) == "Unknown"


def test_get_weather_forecast_success():
    geocode_resp = MagicMock()
    geocode_resp.raise_for_status = MagicMock()
    geocode_resp.json.return_value = {
        "results": [{"latitude": 13.08, "longitude": 80.27, "name": "Chennai"}]
    }

    forecast_resp = MagicMock()
    forecast_resp.raise_for_status = MagicMock()
    forecast_resp.json.return_value = {
        "daily": {
            "time": ["2026-03-03"],
            "temperature_2m_max": [33.0],
            "temperature_2m_min": [22.0],
            "precipitation_sum": [0.0],
            "weathercode": [1],
        }
    }

    with patch("httpx.get", side_effect=[geocode_resp, forecast_resp]):
        result = get_weather_forecast("Chennai", "Tamil Nadu")

    assert "forecast" in result
    assert result["forecast"][0]["max_temp"] == 33.0
    assert result["forecast"][0]["condition"] == "Mainly clear"
    assert result["alerts"] == []


def test_get_weather_forecast_heavy_rain_alert():
    geocode_resp = MagicMock()
    geocode_resp.raise_for_status = MagicMock()
    geocode_resp.json.return_value = {
        "results": [{"latitude": 13.08, "longitude": 80.27, "name": "Chennai"}]
    }

    forecast_resp = MagicMock()
    forecast_resp.raise_for_status = MagicMock()
    forecast_resp.json.return_value = {
        "daily": {
            "time": ["2026-03-03"],
            "temperature_2m_max": [28.0],
            "temperature_2m_min": [22.0],
            "precipitation_sum": [75.0],
            "weathercode": [65],
        }
    }

    with patch("httpx.get", side_effect=[geocode_resp, forecast_resp]):
        result = get_weather_forecast("Chennai", "Tamil Nadu")

    assert any("Heavy rain" in a for a in result["alerts"])


def test_get_weather_forecast_no_geocode_result():
    geocode_resp = MagicMock()
    geocode_resp.raise_for_status = MagicMock()
    geocode_resp.json.return_value = {"results": []}

    with patch("httpx.get", return_value=geocode_resp):
        result = get_weather_forecast("Nowhere", "Nowhere State")

    assert "error" in result
```

**Step 2: Run tests to confirm they fail**

```bash
cd /Users/danieleuchar/workspace/gramvaani
PYTHONPATH=src uv run pytest src/tests/tools/test_weather.py -v
```

Expected: ImportError or AttributeError — `_wmo_condition` doesn't exist yet.

**Step 3: Rewrite weather.py**

```python
# src/app/tools/weather.py
import httpx

from app.cache import cache_get, cache_set

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_WMO_CONDITIONS = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Cloudy",
    45: "Foggy", 48: "Icy fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow",
    80: "Light showers", 81: "Showers", 82: "Heavy showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


def _wmo_condition(code: int) -> str:
    return _WMO_CONDITIONS.get(code, "Unknown")


def get_weather_forecast(district: str, state: str) -> dict:
    cache_key = f"weather:{district}:{state}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        # Step 1: Geocode district + state → lat/lon
        geo = httpx.get(
            _GEOCODE_URL,
            params={"name": f"{district}, {state}, India", "count": 1, "language": "en", "format": "json"},
            timeout=10,
        )
        geo.raise_for_status()
        results = geo.json().get("results", [])
        if not results:
            return {"error": f"Location not found: {district}, {state}"}

        lat = results[0]["latitude"]
        lon = results[0]["longitude"]

        # Step 2: 5-day forecast
        fc = httpx.get(
            _FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
                "timezone": "Asia/Kolkata",
                "forecast_days": 5,
            },
            timeout=10,
        )
        fc.raise_for_status()
        daily = fc.json()["daily"]

        forecast = []
        alerts = []
        for i, date in enumerate(daily["time"]):
            max_temp = daily["temperature_2m_max"][i]
            min_temp = daily["temperature_2m_min"][i]
            rain_mm = daily["precipitation_sum"][i] or 0.0
            condition = _wmo_condition(daily["weathercode"][i])

            forecast.append({
                "date": date,
                "max_temp": max_temp,
                "min_temp": min_temp,
                "rain_mm": rain_mm,
                "condition": condition,
            })

            if rain_mm > 50:
                alerts.append(f"Heavy rain alert ({rain_mm}mm) on {date}")
            if max_temp > 45:
                alerts.append(f"Heatwave alert ({max_temp}°C) on {date}")
            if min_temp < 4:
                alerts.append(f"Frost alert ({min_temp}°C) on {date}")

        result = {"district": district, "state": state, "forecast": forecast, "alerts": alerts}
        cache_set(cache_key, result, ttl_seconds=7200)
        return result

    except Exception as e:
        return {"error": str(e)}
```

**Step 4: Run tests**

```bash
PYTHONPATH=src uv run pytest src/tests/tools/test_weather.py -v
```

Expected: All 5 tests PASS.

**Step 5: Smoke test live API**

```bash
PYTHONPATH=src python3 -c "
from app.tools.weather import get_weather_forecast
import json
print(json.dumps(get_weather_forecast('Chennai', 'Tamil Nadu'), indent=2))
"
```

Expected: 5-day forecast with real temps, no error key.

**Step 6: Commit**

```bash
git add src/app/tools/weather.py src/tests/tools/test_weather.py
git commit -m "feat: replace indianapi.in with Open-Meteo for weather (free, no key)"
```

---

### Task 2: Update filler file naming + multi-variant loader in sarvam_tts.py

**Files:**
- Modify: `src/app/pipeline/sarvam_tts.py`
- Create: `src/tests/pipeline/test_filler_loader.py`

The new filename format is `{lang}_{category}_{index}_{sample_rate}.raw`.
Example: `hi-IN_generic_0_8000.raw`, `ta-IN_mandi_1_8000.raw`.

`get_filler_audio` gains a `category` parameter, picks randomly from available variants.

**Step 1: Write failing tests**

```python
# src/tests/pipeline/test_filler_loader.py
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


def _make_fake_fillers(tmp_path: Path) -> Path:
    """Create fake .raw files in new naming format."""
    filler_dir = tmp_path / "fillers"
    filler_dir.mkdir()
    (filler_dir / "hi-IN_generic_0_8000.raw").write_bytes(b"audio0")
    (filler_dir / "hi-IN_generic_1_8000.raw").write_bytes(b"audio1")
    (filler_dir / "hi-IN_mandi_0_8000.raw").write_bytes(b"mandi0")
    (filler_dir / "ta-IN_generic_0_8000.raw").write_bytes(b"ta_audio0")
    (filler_dir / "en-IN_generic_0_8000.raw").write_bytes(b"en_audio0")
    return filler_dir


def test_get_filler_audio_returns_bytes(tmp_path):
    filler_dir = _make_fake_fillers(tmp_path)
    with patch("app.pipeline.sarvam_tts.FILLERS_DIR", filler_dir):
        # Re-run the cache load
        import app.pipeline.sarvam_tts as tts_mod
        tts_mod.FILLER_AUDIO = tts_mod._load_filler_cache()
        result = tts_mod.get_filler_audio("hi-IN", "generic", 8000)
    assert result in (b"audio0", b"audio1")


def test_get_filler_audio_category_mandi(tmp_path):
    filler_dir = _make_fake_fillers(tmp_path)
    with patch("app.pipeline.sarvam_tts.FILLERS_DIR", filler_dir):
        import app.pipeline.sarvam_tts as tts_mod
        tts_mod.FILLER_AUDIO = tts_mod._load_filler_cache()
        result = tts_mod.get_filler_audio("hi-IN", "mandi", 8000)
    assert result == b"mandi0"


def test_get_filler_audio_falls_back_to_generic(tmp_path):
    filler_dir = _make_fake_fillers(tmp_path)
    with patch("app.pipeline.sarvam_tts.FILLERS_DIR", filler_dir):
        import app.pipeline.sarvam_tts as tts_mod
        tts_mod.FILLER_AUDIO = tts_mod._load_filler_cache()
        # 'weather' category not present for hi-IN → fall back to generic
        result = tts_mod.get_filler_audio("hi-IN", "weather", 8000)
    assert result in (b"audio0", b"audio1")


def test_get_filler_audio_none_category_returns_none(tmp_path):
    filler_dir = _make_fake_fillers(tmp_path)
    with patch("app.pipeline.sarvam_tts.FILLERS_DIR", filler_dir):
        import app.pipeline.sarvam_tts as tts_mod
        tts_mod.FILLER_AUDIO = tts_mod._load_filler_cache()
        result = tts_mod.get_filler_audio("hi-IN", "none", 8000)
    assert result is None
```

**Step 2: Run to confirm failure**

```bash
PYTHONPATH=src uv run pytest src/tests/pipeline/test_filler_loader.py -v
```

Expected: FAIL — `get_filler_audio` doesn't accept `category` yet.

**Step 3: Update `sarvam_tts.py` — loader + get_filler_audio**

Replace `_load_filler_cache` and `get_filler_audio` with:

```python
# New cache shape: {lang: {category: {sample_rate: [bytes, ...]}}}
def _load_filler_cache() -> dict[str, dict[str, dict[int, list[bytes]]]]:
    cache: dict[str, dict[str, dict[int, list[bytes]]]] = {}
    if not FILLERS_DIR.exists():
        return cache
    for path in FILLERS_DIR.glob("*.raw"):
        # filename: {lang}_{category}_{index}_{sample_rate}.raw
        parts = path.stem.split("_")
        if len(parts) == 4:
            lang = f"{parts[0]}-{parts[1]}"   # e.g. hi-IN
            category = parts[2]                # e.g. generic
            sr = int(parts[3])
            audio = path.read_bytes()
            cache.setdefault(lang, {}).setdefault(category, {}).setdefault(sr, []).append(audio)
    return cache


FILLER_AUDIO: dict[str, dict[str, dict[int, list[bytes]]]] = _load_filler_cache()
logger.info("Loaded filler audio for: %s", list(FILLER_AUDIO.keys()))


def get_filler_audio(language_code: str, category: str = "generic", sample_rate: int = 8000) -> bytes | None:
    """Return a randomly chosen pre-generated filler audio for the given category.

    Falls back to 'generic' if the requested category has no files.
    Returns None for category='none' or if no audio is available.
    """
    import random
    if category == "none":
        return None
    lang = language_code if language_code in FILLER_AUDIO else "en-IN"
    lang_cache = FILLER_AUDIO.get(lang, {})
    variants = lang_cache.get(category, {}).get(sample_rate)
    if not variants:
        variants = lang_cache.get("generic", {}).get(sample_rate)
    if not variants:
        return None
    return random.choice(variants)
```

**Step 4: Run tests**

```bash
PYTHONPATH=src uv run pytest src/tests/pipeline/test_filler_loader.py -v
```

Expected: All 4 tests PASS.

**Step 5: Commit**

```bash
git add src/app/pipeline/sarvam_tts.py src/tests/pipeline/test_filler_loader.py
git commit -m "feat: multi-variant filler loader with category + random selection"
```

---

### Task 3: Add filler classifier to pipeline.py

**Files:**
- Modify: `src/app/pipeline/pipeline.py`
- Create: `src/tests/pipeline/test_filler_classifier.py`

**Step 1: Write failing tests**

```python
# src/tests/pipeline/test_filler_classifier.py
import pytest
from app.pipeline.pipeline import _classify_filler


def test_short_ack_is_none():
    assert _classify_filler("Yes") == "none"
    assert _classify_filler("Ok thank you") == "none"
    assert _classify_filler("Thanks") == "none"


def test_price_query_is_mandi():
    assert _classify_filler("What is the tomato price in Tamil Nadu?") == "mandi"
    assert _classify_filler("Mandi rate for onion today") == "mandi"
    assert _classify_filler("wheat price in Punjab") == "mandi"


def test_weather_query_is_weather():
    assert _classify_filler("Will it rain tomorrow in Chennai?") == "weather"
    assert _classify_filler("What is the weather forecast for my district?") == "weather"


def test_scheme_query_is_scheme():
    assert _classify_filler("Am I eligible for PM Kisan scheme?") == "scheme"
    assert _classify_filler("What government subsidies are available?") == "scheme"


def test_open_question_is_generic():
    assert _classify_filler("Tell me about crop rotation for paddy") == "generic"
    assert _classify_filler("When should I sow wheat?") == "generic"
```

**Step 2: Run to confirm failure**

```bash
PYTHONPATH=src uv run pytest src/tests/pipeline/test_filler_classifier.py -v
```

Expected: ImportError — `_classify_filler` not defined yet.

**Step 3: Add `_classify_filler` to pipeline.py**

Add after the existing imports and before `FILLER_PHRASES`:

```python
_MANDI_KW = {
    'price', 'rate', 'mandi', 'market', 'cost',
    'tomato', 'onion', 'wheat', 'rice', 'potato', 'cotton',
    'maize', 'soybean', 'groundnut', 'sugarcane', 'chilli',
}
_WEATHER_KW = {
    'weather', 'rain', 'rainfall', 'forecast', 'temperature',
    'wind', 'storm', 'cloud', 'sunny', 'hot', 'cold', 'humid', 'monsoon',
}
_SCHEME_KW = {
    'scheme', 'subsidy', 'government', 'kisan', 'eligib',
    'benefit', 'loan', 'insurance', 'fasal', 'pm-kisan', 'yojana',
}
_QUESTION_WORDS = {'what', 'when', 'where', 'who', 'why', 'how', 'which', 'is', 'are', 'will', 'can', 'do', 'does'}


def _classify_filler(transcript: str) -> str:
    """Classify transcript into a filler category for context-aware audio selection."""
    words = transcript.lower().split()
    word_set = set(words)

    # Short acknowledgements — no filler needed
    if len(words) <= 4 and '?' not in transcript and not (word_set & _QUESTION_WORDS):
        return 'none'

    if word_set & _MANDI_KW:
        return 'mandi'
    if word_set & _WEATHER_KW:
        return 'weather'
    if word_set & _SCHEME_KW:
        return 'scheme'

    return 'generic'
```

Also remove `FILLER_PHRASES` and `DEFAULT_FILLER` constants (no longer used).

**Step 4: Update both pipeline functions to use classifier**

In `process_turn` — replace the filler block (lines ~122–126):

```python
    # 2. Filler — classify transcript to pick contextual audio
    filler_category = _classify_filler(english_transcript)
    filler_audio = get_filler_audio(detected_lang, filler_category, sample_rate=8000)
    if filler_audio and audio_send_callback:
        await audio_send_callback(filler_audio)
```

In `process_turn_streaming` — replace filler block (lines ~192–196):

```python
    # 2. Filler — classify transcript to pick contextual audio
    filler_category = _classify_filler(transcript)
    filler = get_filler_audio(detected_lang, filler_category, sample_rate=sample_rate)
    if filler:
        arr = np.frombuffer(filler, dtype=np.int16).copy()
        await audio_queue.put((sample_rate, arr))
```

**Step 5: Run tests**

```bash
PYTHONPATH=src uv run pytest src/tests/pipeline/test_filler_classifier.py -v
```

Expected: All 5 tests PASS.

**Step 6: Commit**

```bash
git add src/app/pipeline/pipeline.py src/tests/pipeline/test_filler_classifier.py
git commit -m "feat: context-aware filler classifier — none/mandi/weather/scheme/generic"
```

---

### Task 4: Update filler generation script + generate new audio files

**Files:**
- Modify: `scripts/generate_fillers.py`
- Delete: old `src/app/assets/fillers/*.raw` files (old naming)
- Create: new `src/app/assets/fillers/` `.raw` files (new naming)

**Step 1: Update generate_fillers.py**

Replace the entire file content:

```python
"""
Generate filler phrase audio files for all categories using bulbul:v2 + anushka.
Saves raw PCM files to src/app/assets/fillers/ using naming:
  {lang}_{category}_{index}_{sample_rate}.raw

Run once:
    PYTHONPATH=src uv run python scripts/generate_fillers.py

Commit the generated files — no API calls needed on subsequent runs.
"""
import base64
import httpx
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("SARVAM_API_KEY", "")
if not API_KEY:
    print("ERROR: SARVAM_API_KEY not set in .env")
    sys.exit(1)

ASSETS_DIR = Path(__file__).parent.parent / "src" / "app" / "assets" / "fillers"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

FILLERS: dict[str, dict[str, list[str]]] = {
    "hi-IN": {
        "generic": [
            "हाँ जी, एक पल।",
            "देखते हैं।",
            "समझ गया, थोड़ा रुकिए।",
        ],
        "mandi": [
            "मंडी भाव देख रहा हूँ।",
            "कीमत जांच रहा हूँ।",
        ],
        "weather": [
            "मौसम की जानकारी ले रहा हूँ।",
        ],
        "scheme": [
            "सरकारी योजनाएं देख रहा हूँ।",
        ],
    },
    "ta-IN": {
        "generic": [
            "சரி, ஒரு நிமிடம்.",
            "பார்க்கிறேன்.",
            "புரிந்தது, கொஞ்சம் நிறுத்துங்கள்.",
        ],
        "mandi": [
            "விலை சரிபார்க்கிறேன்.",
            "மண்டி விலை பார்க்கிறேன்.",
        ],
        "weather": [
            "வானிலை தகவல் எடுக்கிறேன்.",
        ],
        "scheme": [
            "அரசு திட்டங்கள் பார்க்கிறேன்.",
        ],
    },
    "en-IN": {
        "generic": [
            "One moment.",
            "Let me check.",
        ],
        "mandi": [
            "Checking market prices.",
        ],
        "weather": [
            "Getting weather information.",
        ],
        "scheme": [
            "Looking up government schemes.",
        ],
    },
}

SPEAKER = "anushka"
MODEL   = "bulbul:v2"
SAMPLE_RATES = [8000, 22050]


def generate(lang: str, text: str, sample_rate: int) -> bytes:
    resp = httpx.post(
        "https://api.sarvam.ai/text-to-speech",
        headers={"api-subscription-key": API_KEY},
        json={
            "inputs": [text],
            "target_language_code": lang,
            "speaker": SPEAKER,
            "pace": 1.0,
            "speech_sample_rate": sample_rate,
            "model": MODEL,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return base64.b64decode(resp.json()["audios"][0])


print(f"Generating fillers with {MODEL} / {SPEAKER}...")
print(f"Output: {ASSETS_DIR}\n")

for lang, categories in FILLERS.items():
    for category, phrases in categories.items():
        for idx, text in enumerate(phrases):
            print(f"[{lang}] [{category}] [{idx}] {text!r}")
            for sr in SAMPLE_RATES:
                audio = generate(lang, text, sr)
                filename = f"{lang.replace('-', '_')}_{category}_{idx}_{sr}.raw"
                path = ASSETS_DIR / filename
                path.write_bytes(audio)
                print(f"  {sr}Hz → {filename} ({len(audio):,} bytes)")

print("\nDone. Commit the generated files to git.")
```

Note: the lang part uses underscore in the filename (e.g. `hi_IN_generic_0_8000.raw`) because `-` in stem splits awkwardly. The loader in `sarvam_tts.py` joins parts[0] and parts[1] with `-` — update the loader to handle this.

**Step 2: Update loader in sarvam_tts.py to handle `hi_IN` → `hi-IN` conversion**

In `_load_filler_cache`, change the lang parsing line:

```python
# filename: {lang_underscored}_{category}_{index}_{sample_rate}.raw
# e.g. hi_IN_generic_0_8000
parts = path.stem.split("_")
if len(parts) == 5:
    lang = f"{parts[0]}-{parts[1]}"   # hi_IN → hi-IN
    category = parts[2]
    sr = int(parts[4])
```

Also update the test helpers in `test_filler_loader.py` to use the new underscore naming:

```python
(filler_dir / "hi_IN_generic_0_8000.raw").write_bytes(b"audio0")
(filler_dir / "hi_IN_generic_1_8000.raw").write_bytes(b"audio1")
(filler_dir / "hi_IN_mandi_0_8000.raw").write_bytes(b"mandi0")
(filler_dir / "ta_IN_generic_0_8000.raw").write_bytes(b"ta_audio0")
(filler_dir / "en_IN_generic_0_8000.raw").write_bytes(b"en_audio0")
```

**Step 3: Delete old `.raw` files**

```bash
rm src/app/assets/fillers/hi-IN_8000.raw
rm src/app/assets/fillers/hi-IN_22050.raw
rm src/app/assets/fillers/ta-IN_8000.raw
rm src/app/assets/fillers/ta-IN_22050.raw
rm src/app/assets/fillers/en-IN_8000.raw
rm src/app/assets/fillers/en-IN_22050.raw
```

**Step 4: Run all tests with updated loader**

```bash
PYTHONPATH=src uv run pytest src/tests/pipeline/test_filler_loader.py -v
```

Expected: All 4 tests PASS.

**Step 5: Generate new audio files**

```bash
PYTHONPATH=src uv run python scripts/generate_fillers.py
```

Expected: Prints each phrase + file size. Should create ~36 files (3 langs × ~4 categories × up to 3 phrases × 2 sample rates).

**Step 6: Verify files created**

```bash
ls src/app/assets/fillers/ | head -20
```

Expected: Files like `hi_IN_generic_0_8000.raw`, `ta_IN_mandi_1_22050.raw`, etc.

**Step 7: Commit everything**

```bash
git add scripts/generate_fillers.py src/app/assets/fillers/ src/app/pipeline/sarvam_tts.py src/tests/pipeline/test_filler_loader.py
git commit -m "feat: context-aware filler audio — 3 langs × 4 categories × multiple variants"
```

---

### Task 5: Full test run + smoke test

**Step 1: Run all tests**

```bash
PYTHONPATH=src uv run pytest src/tests/ -v
```

Expected: All tests PASS.

**Step 2: Smoke test weather live**

```bash
PYTHONPATH=src python3 -c "
from app.tools.weather import get_weather_forecast
import json
print(json.dumps(get_weather_forecast('Coimbatore', 'Tamil Nadu'), indent=2))
"
```

Expected: 5-day forecast, no error key.

**Step 3: Smoke test filler classification + loading**

```bash
PYTHONPATH=src python3 -c "
from app.pipeline.pipeline import _classify_filler
tests = [
    ('Yes', 'none'),
    ('What is the tomato price in Tamil Nadu?', 'mandi'),
    ('Will it rain tomorrow?', 'weather'),
    ('Am I eligible for PM Kisan?', 'scheme'),
    ('When should I sow wheat?', 'generic'),
]
for text, expected in tests:
    got = _classify_filler(text)
    status = 'OK' if got == expected else f'FAIL (expected {expected})'
    print(f'[{status}] {text!r} → {got}')
"
```

Expected: All 5 lines show `OK`.

**Step 4: Final commit if any cleanup**

```bash
git add -A
git commit -m "chore: final cleanup after context-aware fillers + Open-Meteo"
```
