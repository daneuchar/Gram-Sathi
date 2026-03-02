import asyncio
import logging
from collections.abc import Callable, Awaitable

from app.pipeline.nova_client import NovaClient
from app.pipeline.sarvam_asr import transcribe
from app.pipeline.sarvam_translate import to_english, from_english, ENGLISH_LANGS
from app.pipeline.sarvam_tts import synthesize

logger = logging.getLogger(__name__)

# Filler phrases — spoken immediately after ASR while Nova processes
# Short, natural, language-appropriate
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
    """Process one voice turn with translate-in / translate-out flow:

    User speech (any lang)
        → ASR → transcript in user lang
        → translate to English          (skip if user speaks English)
        → Nova (English in, English out)
        → translate back to user lang   (skip if user speaks English)
        → TTS → audio in user lang

    Returns (original_transcript, detected_language_code).
    """
    if not audio_bytes:
        return ("", language_code)

    # 1. ASR — get transcript in farmer's language
    asr_result = await transcribe(audio_bytes, language_code)
    transcript = asr_result["transcript"]
    detected_lang = asr_result["language_code"]

    if not transcript.strip():
        return ("", detected_lang)

    # 2. Start filler TTS + translation to English concurrently
    filler_text = FILLER_PHRASES.get(detected_lang, DEFAULT_FILLER)
    filler_task = asyncio.create_task(synthesize(filler_text, detected_lang))

    is_english = detected_lang in ENGLISH_LANGS
    if is_english:
        english_transcript = transcript
    else:
        english_transcript = await to_english(transcript, detected_lang)
        logger.debug("Translated to English: %s", english_transcript)

    # 3. Play filler as soon as it's ready (farmer hears something while Nova thinks)
    filler_audio = await filler_task
    if audio_send_callback:
        await audio_send_callback(filler_audio)

    # 4. Nova — receives and responds in English
    messages = list(conversation_history)
    messages.append({"role": "user", "content": [{"text": english_transcript}]})

    english_response = await nova_client.generate(
        user_text="",
        conversation_history=messages,
        language_code="en-IN",
    )

    if not english_response or isinstance(english_response, dict):
        return (transcript, detected_lang)

    logger.debug("Nova English response: %s", english_response)

    # 5. Translate response back to farmer's language
    if is_english:
        response_in_user_lang = english_response
    else:
        response_in_user_lang = await from_english(english_response, detected_lang)
        logger.debug("Translated to %s: %s", detected_lang, response_in_user_lang)

    # 6. Single TTS call — full response, no sentence splits, no pauses
    if response_in_user_lang and audio_send_callback:
        response_audio = await synthesize(response_in_user_lang, detected_lang)
        await audio_send_callback(response_audio)

    return (transcript, detected_lang)
