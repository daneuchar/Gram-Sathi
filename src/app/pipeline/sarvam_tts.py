import asyncio
import base64
import io
import logging
from collections.abc import AsyncGenerator

import httpx
from pydub import AudioSegment
from sarvamai import AsyncSarvamAI

from app.config import settings

logger = logging.getLogger(__name__)

TTS_REST_URL = "https://api.sarvam.ai/text-to-speech"

# bulbul:v3 speakers — for REST API (filler phrases, best quality)
SPEAKER_MAP_V3 = {
    "hi-IN": "kavya",
    "ta-IN": "kavitha",
    "te-IN": "gokul",
    "mr-IN": "roopa",
    "kn-IN": "shruti",
    "en-IN": "anand",
    "en-US": "anand",
    "default": "kavya",
}

# bulbul:v2 speakers — for WebSocket streaming (v2 only supported on stream endpoint)
# Female: anushka, manisha, vidya, arya | Male: abhilash, karun, hitesh
SPEAKER_MAP_V2 = {
    "hi-IN": "anushka",
    "ta-IN": "anushka",
    "te-IN": "abhilash",
    "mr-IN": "manisha",
    "kn-IN": "vidya",
    "en-IN": "anushka",
    "en-US": "anushka",
    "default": "anushka",
}


async def synthesize(text: str, language_code: str, sample_rate: int = 8000) -> bytes:
    """REST TTS using bulbul:v3 — highest quality, used for filler phrases.
    Returns full audio bytes (no streaming). sample_rate=8000 for Exotel phone calls.
    """
    speaker = SPEAKER_MAP_V3.get(language_code, SPEAKER_MAP_V3["default"])
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


async def synthesize_streaming(
    text: str,
    language_code: str,
    sample_rate: int = 8000,
) -> AsyncGenerator[bytes, None]:
    """WebSocket streaming TTS using sarvamai SDK + bulbul:v2.

    First audio arrives in ~900ms. Yields decoded PCM bytes per chunk.
    The caller writes each chunk to an audio stream immediately — no waiting for full synthesis.

    Note: Uses bulbul:v2 (only model supported on streaming endpoint).
    Uses MP3 codec (only codec supported) + pydub decode per chunk.
    sample_rate: 8000 for Exotel phone calls, 22050 for local playback.
    """
    speaker = SPEAKER_MAP_V2.get(language_code, SPEAKER_MAP_V2["default"])
    client = AsyncSarvamAI(api_subscription_key=settings.sarvam_api_key)

    async with client.text_to_speech_streaming.connect(
        model="bulbul:v2",
        send_completion_event=True,
    ) as ws:
        await ws.configure(
            target_language_code=language_code,
            speaker=speaker,
            pace=1.0,
            speech_sample_rate=sample_rate,
            output_audio_codec="mp3",
            output_audio_bitrate="128k",
            min_buffer_size=50,
            max_chunk_length=200,
        )
        await ws.convert(text)
        await ws.flush()

        from sarvamai import AudioOutput
        async for message in ws:
            if isinstance(message, AudioOutput):
                mp3_bytes = base64.b64decode(message.data.audio)
                # Decode MP3 chunk → PCM at target sample rate
                seg = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
                if seg.frame_rate != sample_rate:
                    seg = seg.set_frame_rate(sample_rate)
                if seg.channels != 1:
                    seg = seg.set_channels(1)
                pcm_bytes = seg.raw_data
                yield pcm_bytes
            else:
                # EventResponse (stream_complete) or ErrorResponse
                break
