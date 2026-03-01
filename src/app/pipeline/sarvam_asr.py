import base64
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ASR_URL = "https://api.sarvam.ai/speech-to-text"


async def transcribe(audio_bytes: bytes, language_code: str) -> dict:
    """Transcribe audio using Sarvam Saaras v3.

    Returns dict with keys: transcript, language_code.
    """
    audio_b64 = base64.b64encode(audio_bytes).decode()

    payload = {
        "model": "saaras:v3",
        "audio": audio_b64,
        "language_code": language_code,
        "with_timestamps": False,
    }

    headers = {
        "api-subscription-key": settings.sarvam_api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(ASR_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    return {
        "transcript": data.get("transcript", ""),
        "language_code": data.get("language_code", language_code),
    }
