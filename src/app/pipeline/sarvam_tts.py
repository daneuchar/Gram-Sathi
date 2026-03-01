import base64
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TTS_URL = "https://api.sarvam.ai/text-to-speech"

# bulbul:v2 speakers — language-agnostic, any speaker works for any Indian language.
# Picked based on voice character: female default, male alternative per language.
SPEAKER_MAP = {
    "hi-IN": "anushka",    # female Hindi
    "ta-IN": "anushka",    # female Tamil
    "te-IN": "abhilash",   # male Telugu
    "mr-IN": "manisha",    # female Marathi
    "kn-IN": "vidya",      # female Kannada
    "bn-IN": "arya",       # female Bengali
    "gu-IN": "anushka",
    "pa-IN": "abhilash",
    "default": "anushka",
}


async def synthesize(text: str, language_code: str) -> bytes:
    """Synthesize text to PCM audio bytes using Sarvam Bulbul v2."""
    speaker = SPEAKER_MAP.get(language_code, SPEAKER_MAP["default"])

    payload = {
        "inputs": [text],
        "target_language_code": language_code,
        "speaker": speaker,
        "pace": 0.9,
        "speech_sample_rate": 8000,
        "enable_preprocessing": True,
        "model": "bulbul:v2",
    }

    headers = {"api-subscription-key": settings.sarvam_api_key}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(TTS_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    audio_b64 = data["audios"][0]
    return base64.b64decode(audio_b64)
