import asyncio
import logging
import re
from collections.abc import Callable, Awaitable

from app.pipeline.nova_client import NovaClient
from app.pipeline.sarvam_asr import transcribe
from app.pipeline.sarvam_tts import synthesize

logger = logging.getLogger(__name__)

# Only English, Hindi, Tamil for now
FILLER_PHRASES = {
    "hi-IN": "हाँ जी, एक पल।",
    "ta-IN": "சரி, ஒரு நிமிடம்.",
    "en-IN": "One moment.",
    "en-US": "One moment.",
}

# Strip [LANG: xx-XX] tags that Nova sometimes echoes back
LANG_TAG_RE = re.compile(r"\[LANG:\s*[a-z]{2}-[A-Z]{2}\]\s*", re.IGNORECASE)

nova_client = NovaClient()


def _clean_response(text: str) -> str:
    """Remove any [LANG: xx-XX] tags Nova echoes back before sending to TTS."""
    return LANG_TAG_RE.sub("", text).strip()


async def process_turn(
    audio_bytes: bytes,
    farmer_profile: dict | None,
    conversation_history: list[dict],
    language_code: str,
    tools: list[dict] | None = None,
    tool_executor: Callable | None = None,
    audio_send_callback: Callable[[bytes], Awaitable[None]] | None = None,
) -> tuple[str, str]:
    """Process one voice turn: ASR -> filler -> Nova -> TTS (single call, no pauses).

    Returns (transcript, detected_language_code).
    """
    if not audio_bytes:
        return ("", language_code)

    # 1. ASR
    asr_result = await transcribe(audio_bytes, language_code)
    transcript = asr_result["transcript"]
    detected_lang = asr_result["language_code"]

    if not transcript.strip():
        return ("", detected_lang)

    # 2. Filler phrase + Nova run concurrently:
    #    - filler TTS starts immediately so farmer hears something fast
    #    - Nova call starts at the same time in the background
    tagged_transcript = f"[LANG: {detected_lang}] {transcript}"
    messages = list(conversation_history)
    messages.append({"role": "user", "content": [{"text": tagged_transcript}]})

    filler = FILLER_PHRASES.get(detected_lang, "One moment.")

    # Run filler TTS and Nova call concurrently
    filler_audio_task = asyncio.create_task(synthesize(filler, detected_lang))
    nova_task = asyncio.create_task(
        nova_client.generate(
            user_text="",
            conversation_history=messages,
            language_code=detected_lang,
        )
    )

    # Play filler as soon as it's ready
    filler_audio = await filler_audio_task
    if audio_send_callback:
        await audio_send_callback(filler_audio)

    # Wait for Nova full response
    nova_response = await nova_task
    if isinstance(nova_response, dict):
        # Tool call — handle and get follow-up
        nova_response = str(nova_response)

    response_text = _clean_response(nova_response)

    # 3. Single TTS call for full response — no pauses between sentences
    if response_text and audio_send_callback:
        response_audio = await synthesize(response_text, detected_lang)
        await audio_send_callback(response_audio)

    return (transcript, detected_lang)
