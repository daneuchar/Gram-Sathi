import base64
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TTS_URL = "https://api.sarvam.ai/text-to-speech"

# bulbul:v3 speakers — language-specific voices for maximum naturalness
SPEAKER_MAP = {
    "hi-IN": "kavya",      # Hindi female — natural, warm
    "ta-IN": "kavitha",    # Tamil female — native Tamil speaker
    "te-IN": "gokul",      # Telugu male — native Telugu speaker
    "mr-IN": "roopa",      # Marathi female
    "kn-IN": "shruti",     # Kannada female
    "bn-IN": "kabir",      # Bengali male
    "gu-IN": "manan",      # Gujarati male
    "pa-IN": "aayan",      # Punjabi male
    "en-IN": "anand",      # English (Indian accent)
    "en-US": "anand",
    "default": "kavya",
}


async def synthesize(text: str, language_code: str, sample_rate: int = 8000) -> bytes:
    """Synthesize text to PCM audio using Sarvam Bulbul v3.

    bulbul:v3 improvements over v2:
    - More natural prosody and expressiveness
    - 45 language-specific speakers
    - temperature parameter for voice variation (higher = more natural)
    - Better Indian language rendering

    sample_rate: 8000 for phone calls (Exotel), 22050 for local playback
    """
    speaker = SPEAKER_MAP.get(language_code, SPEAKER_MAP["default"])

    payload = {
        "inputs": [text],
        "target_language_code": language_code,
        "speaker": speaker,
        "pace": 1.0,              # natural pace (was 0.9 — slightly slow)
        "speech_sample_rate": sample_rate,
        "model": "bulbul:v3",
        "temperature": 0.8,       # v3 only — higher = more expressive, less robotic
    }

    headers = {"api-subscription-key": settings.sarvam_api_key}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(TTS_URL, json=payload, headers=headers)
        resp.raise_for_status()

    audio_b64 = resp.json()["audios"][0]
    return base64.b64decode(audio_b64)
