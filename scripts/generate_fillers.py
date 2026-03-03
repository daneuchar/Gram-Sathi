"""
Generate filler phrase audio files for all categories using bulbul:v2 + anushka.
Saves raw PCM files to src/app/assets/fillers/ using naming:
  {lang_underscored}_{category}_{index}_{sample_rate}.raw
  e.g. hi_IN_generic_0_8000.raw

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
