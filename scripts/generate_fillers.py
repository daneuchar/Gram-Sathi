"""
Generate filler phrase audio files using bulbul:v2 + anushka (matching streaming voice).
Saves MP3 files to src/app/assets/fillers/.

Run once:
    PYTHONPATH=src uv run python scripts/generate_fillers.py

Files are committed to git — no API calls needed on subsequent runs.
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

# Filler phrases — same model (bulbul:v2) and speaker (anushka) as streaming TTS
# so voice is consistent with the response audio
FILLERS = {
    "hi-IN": "हाँ जी, एक पल।",
    "ta-IN": "சரி, ஒரு நிமிடம்.",
    "en-IN": "One moment.",
}

SPEAKER = "anushka"   # matches streaming TTS speaker
MODEL   = "bulbul:v2" # matches streaming TTS model


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


print(f"Generating filler audio with {MODEL} / {SPEAKER}...")
print(f"Output: {ASSETS_DIR}\n")

for lang, text in FILLERS.items():
    print(f"[{lang}] {text!r}")

    # 8kHz — for Exotel phone calls
    audio_8k = generate(lang, text, 8000)
    path_8k = ASSETS_DIR / f"{lang}_8000.raw"
    path_8k.write_bytes(audio_8k)
    print(f"  8kHz  → {path_8k.name} ({len(audio_8k):,} bytes)")

    # 22050Hz — for local playback / testing
    audio_22k = generate(lang, text, 22050)
    path_22k = ASSETS_DIR / f"{lang}_22050.raw"
    path_22k.write_bytes(audio_22k)
    print(f"  22050Hz → {path_22k.name} ({len(audio_22k):,} bytes)")

print("\nDone. Commit the generated files to git.")
print("They load from disk — no API call needed on startup.")
