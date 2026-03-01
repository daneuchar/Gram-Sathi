import base64
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TTS_URL = "https://api.sarvam.ai/text-to-speech"

SPEAKER_MAP = {
    "hi-IN": "meera",
    "ta-IN": "pavithra",
    "te-IN": "arvind",
    "mr-IN": "aarohi",
    "kn-IN": "suresh",
    "bn-IN": "riya",
}


async def synthesize(text: str, language_code: str) -> bytes:
    """Synthesize text to PCM audio bytes using Sarvam Bulbul v1."""
    speaker = SPEAKER_MAP.get(language_code, "meera")

    payload = {
        "model": "bulbul:v1",
        "text": text,
        "language_code": language_code,
        "speaker": speaker,
        "pace": 0.9,
        "speech_sample_rate": 8000,
    }

    headers = {
        "api-subscription-key": settings.sarvam_api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(TTS_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    audio_b64 = data.get("audio", "")
    return base64.b64decode(audio_b64)
