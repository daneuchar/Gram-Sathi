import asyncio
import logging
import re
from collections.abc import Callable, Awaitable

from num2words import num2words

from app.pipeline.nova_client import NovaClient
from app.pipeline.sarvam_asr import transcribe
from app.pipeline.sarvam_translate import from_english, ENGLISH_LANGS
from app.pipeline.sarvam_tts import get_filler_audio, synthesize_streaming
from app.tools.registry import NOVA_TOOLS, execute_tool

logger = logging.getLogger(__name__)

FILLER_PHRASES = {
    "hi-IN": "हाँ जी, एक पल।",
    "ta-IN": "சரி, ஒரு நிமிடம்.",
    "en-IN": "One moment.",
    "en-US": "One moment.",
}
DEFAULT_FILLER = "One moment."

nova_client = NovaClient()

_NUMBER_RE = re.compile(r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b|\b\d+(?:\.\d+)?\b')


def _expand_numbers(text: str) -> str:
    """Replace Arabic numerals with English words so Sarvam translate
    converts them to native-language number words (e.g. 1200 → 'one thousand
    two hundred' → 'बारह सौ' in Hindi)."""
    def _replace(m: re.Match) -> str:
        raw = m.group().replace(",", "")
        try:
            n = float(raw)
            if n == int(n):
                return num2words(int(n), lang="en")
            return num2words(n, lang="en")
        except Exception:
            return m.group()
    return _NUMBER_RE.sub(_replace, text)


async def process_turn(
    audio_bytes: bytes,
    farmer_profile: dict | None,
    conversation_history: list[dict],
    language_code: str,
    tools: list[dict] | None = None,
    tool_executor: Callable | None = None,
    audio_send_callback: Callable[[bytes], Awaitable[None]] | None = None,
) -> tuple[str, str, str]:
    """Process one voice turn.

    Pipeline:
        Audio → saaras:v3 (mode=translate) → English text   ← single call, replaces ASR + translate
        English text → Nova 2 Lite → English response
        English response → sarvam-translate → user's language
        User's language text → bulbul:v3 → audio

    For English input: mode=transcribe, skip translate steps entirely.
    Returns (english_transcript, detected_language_code, english_response).
    """
    if not audio_bytes:
        return ("", language_code, "")

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
        return ("", detected_lang, "")

    # Recheck if English now that we have detected language
    is_english = detected_lang in ENGLISH_LANGS

    # 2. Filler — load from pre-generated file (0ms, no API call)
    #    Same voice as streaming response (bulbul:v2 anushka)
    filler_audio = get_filler_audio(detected_lang, sample_rate=8000)
    if filler_audio and audio_send_callback:
        await audio_send_callback(filler_audio)

    # Nova runs while filler is playing
    messages = list(conversation_history)
    messages.append({"role": "user", "content": [{"text": english_transcript}]})
    nova_task = asyncio.create_task(
        nova_client.generate(user_text="", conversation_history=messages, tools=NOVA_TOOLS, tool_executor=execute_tool)
    )

    english_response = await nova_task
    if not english_response or isinstance(english_response, dict):
        return (english_transcript, detected_lang, "")

    # 3. Expand digits to English words so translation yields native number words
    english_response = _expand_numbers(english_response)

    # 4. Translate English response → farmer's language (skip if English)
    if is_english:
        response_in_user_lang = english_response
    else:
        response_in_user_lang = await from_english(english_response, detected_lang)

    # 5. WebSocket streaming TTS — first audio chunk in ~400ms, no waiting for full synthesis
    if response_in_user_lang and audio_send_callback:
        async for audio_chunk in synthesize_streaming(response_in_user_lang, detected_lang):
            await audio_send_callback(audio_chunk)

    return (english_transcript, detected_lang, english_response)
