import io
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ASR_URL = "https://api.sarvam.ai/speech-to-text"


async def transcribe(
    audio_bytes: bytes,
    language_code: str,
    mode: str = "translate",
) -> dict:
    """Transcribe audio using Sarvam Saaras v3.

    mode="translate"  → returns English transcript directly (ASR + translation in one call)
                        used for non-English input — saves a separate translate API call
    mode="transcribe" → returns transcript in the same language as input
                        used for English input (no translation needed)

    Returns dict with keys:
        transcript    - text output (English if mode=translate)
        language_code - detected language of the audio (e.g. "hi-IN")
    """
    headers = {"api-subscription-key": settings.sarvam_api_key}

    # In translate mode, omit language_code so Sarvam auto-detects the spoken language.
    # When language_code is specified, Sarvam echoes it back verbatim (no detection).
    # In transcribe mode (English-only), we always know the language so we send it.
    form_data: dict = {
        "model": "saaras:v3",
        "with_timestamps": "false",
        "mode": mode,
    }
    if mode == "transcribe":
        form_data["language_code"] = language_code

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            ASR_URL,
            headers=headers,
            data=form_data,
            files={"file": ("audio.wav", io.BytesIO(audio_bytes), "audio/wav")},
        )
        resp.raise_for_status()
        data = resp.json()

    return {
        "transcript": data.get("transcript", ""),
        "language_code": data.get("language_code", language_code),
    }
