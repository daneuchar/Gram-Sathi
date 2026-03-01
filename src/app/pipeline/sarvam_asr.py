import io
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ASR_URL = "https://api.sarvam.ai/speech-to-text"


async def transcribe(audio_bytes: bytes, language_code: str) -> dict:
    """Transcribe audio using Sarvam Saaras v3 (multipart file upload).

    Returns dict with keys: transcript, language_code.
    """
    headers = {"api-subscription-key": settings.sarvam_api_key}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            ASR_URL,
            headers=headers,
            data={
                "model": "saaras:v3",
                "language_code": language_code,
                "with_timestamps": "false",
            },
            files={"file": ("audio.wav", io.BytesIO(audio_bytes), "audio/wav")},
        )
        resp.raise_for_status()
        data = resp.json()

    return {
        "transcript": data.get("transcript", ""),
        "language_code": data.get("language_code", language_code),
    }
