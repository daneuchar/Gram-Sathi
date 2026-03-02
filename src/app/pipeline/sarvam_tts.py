import base64
import json
import logging
from collections.abc import AsyncGenerator

import httpx
import websockets

from app.config import settings

logger = logging.getLogger(__name__)

TTS_REST_URL = "https://api.sarvam.ai/text-to-speech"
TTS_WS_URL   = "wss://api.sarvam.ai/text-to-speech/ws"

# Language → speaker mapping (bulbul:v3 / bulbul:v3-beta)
SPEAKER_MAP = {
    "hi-IN": "kavya",
    "ta-IN": "kavitha",
    "te-IN": "gokul",
    "mr-IN": "roopa",
    "kn-IN": "shruti",
    "bn-IN": "kabir",
    "gu-IN": "manan",
    "pa-IN": "aayan",
    "en-IN": "anand",
    "en-US": "anand",
    "default": "kavya",
}


async def synthesize_streaming(
    text: str,
    language_code: str,
    sample_rate: int = 8000,
) -> AsyncGenerator[bytes, None]:
    """Stream TTS audio chunks via Sarvam WebSocket API.

    First audio chunk arrives in ~400ms instead of waiting for full synthesis.
    Yields raw PCM bytes (linear16) as they arrive — caller plays each chunk immediately.

    Uses bulbul:v3-beta (WebSocket endpoint only supports v2/v3-beta).
    """
    speaker = SPEAKER_MAP.get(language_code, SPEAKER_MAP["default"])
    uri = f"{TTS_WS_URL}?model=bulbul:v3-beta&send_completion_event=true"
    headers = {"Api-Subscription-Key": settings.sarvam_api_key}

    async with websockets.connect(uri, additional_headers=headers) as ws:
        # 1. Config
        await ws.send(json.dumps({"type": "config", "data": {
            "target_language_code": language_code,
            "speaker": speaker,
            "pace": 1.0,
            "speech_sample_rate": str(sample_rate),
            "model": "bulbul:v3-beta",
            "output_audio_codec": "linear16",
        }}))

        # 2. Send text + flush
        await ws.send(json.dumps({"type": "text", "data": {"text": text}}))
        await ws.send(json.dumps({"type": "flush"}))

        # 3. Stream audio chunks until completion event or connection closes
        try:
            async for message in ws:
                msg = json.loads(message)
                if msg["type"] == "audio":
                    yield base64.b64decode(msg["data"]["audio"])
                elif msg["type"] == "event":
                    break  # stream_complete or similar — done
                elif msg["type"] == "error":
                    logger.error("Sarvam WS TTS error: %s", msg)
                    break
        except websockets.exceptions.ConnectionClosed:
            pass  # server closed connection — all audio received


async def synthesize(text: str, language_code: str, sample_rate: int = 8000) -> bytes:
    """Synthesize full audio via REST (used for short filler phrases at startup).

    For longer responses use synthesize_streaming() for lower perceived latency.
    sample_rate: 8000 for Exotel phone calls, 22050 for local playback.
    """
    speaker = SPEAKER_MAP.get(language_code, SPEAKER_MAP["default"])

    payload = {
        "inputs": [text],
        "target_language_code": language_code,
        "speaker": speaker,
        "pace": 1.0,
        "speech_sample_rate": sample_rate,
        "model": "bulbul:v3",
        "temperature": 0.8,
    }

    headers = {"api-subscription-key": settings.sarvam_api_key}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(TTS_REST_URL, json=payload, headers=headers)
        resp.raise_for_status()

    return base64.b64decode(resp.json()["audios"][0])
