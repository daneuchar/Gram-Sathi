import asyncio
import logging
from collections.abc import Callable, Awaitable

from app.pipeline.nova_client import NovaClient
from app.pipeline.sarvam_asr import transcribe
from app.pipeline.sarvam_translate import from_english, ENGLISH_LANGS
from app.pipeline.sarvam_tts import synthesize

logger = logging.getLogger(__name__)

FILLER_PHRASES = {
    "hi-IN": "हाँ जी, एक पल।",
    "ta-IN": "சரி, ஒரு நிமிடம்.",
    "en-IN": "One moment.",
    "en-US": "One moment.",
}
DEFAULT_FILLER = "One moment."

nova_client = NovaClient()


async def process_turn(
    audio_bytes: bytes,
    farmer_profile: dict | None,
    conversation_history: list[dict],
    language_code: str,
    tools: list[dict] | None = None,
    tool_executor: Callable | None = None,
    audio_send_callback: Callable[[bytes], Awaitable[None]] | None = None,
) -> tuple[str, str]:
    """Process one voice turn.

    Pipeline:
        Audio → saaras:v3 (mode=translate) → English text   ← single call, replaces ASR + translate
        English text → Nova 2 Lite → English response
        English response → sarvam-translate → user's language
        User's language text → bulbul:v3 → audio

    For English input: mode=transcribe, skip translate steps entirely.
    Returns (english_transcript, detected_language_code).
    """
    if not audio_bytes:
        return ("", language_code)

    is_english = language_code in ENGLISH_LANGS

    # 1. ASR — one call handles both transcription and translation to English
    asr_result = await transcribe(
        audio_bytes,
        language_code,
        mode="transcribe" if is_english else "translate",
    )
    english_transcript = asr_result["transcript"]
    detected_lang = asr_result["language_code"]

    if not english_transcript.strip():
        return ("", detected_lang)

    # Recheck if English now that we have detected language
    is_english = detected_lang in ENGLISH_LANGS

    # 2. Filler TTS + Nova run concurrently — farmer hears filler immediately
    filler_text = FILLER_PHRASES.get(detected_lang, DEFAULT_FILLER)
    filler_task = asyncio.create_task(synthesize(filler_text, detected_lang))

    messages = list(conversation_history)
    messages.append({"role": "user", "content": [{"text": english_transcript}]})
    nova_task = asyncio.create_task(
        nova_client.generate(user_text="", conversation_history=messages)
    )

    filler_audio = await filler_task
    if audio_send_callback:
        await audio_send_callback(filler_audio)

    english_response = await nova_task
    if not english_response or isinstance(english_response, dict):
        return (english_transcript, detected_lang)

    # 3. Translate English response → farmer's language (skip if English)
    if is_english:
        response_in_user_lang = english_response
    else:
        response_in_user_lang = await from_english(english_response, detected_lang)

    # 4. Single TTS call — full response, no pauses
    if response_in_user_lang and audio_send_callback:
        response_audio = await synthesize(response_in_user_lang, detected_lang)
        await audio_send_callback(response_audio)

    return (english_transcript, detected_lang)
