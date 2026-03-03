import asyncio
import logging
import re
from collections.abc import Callable, Awaitable

import numpy as np

from num2words import num2words

from app.pipeline.nova_client import NovaClient
from app.pipeline.sarvam_asr import transcribe
from app.pipeline.sarvam_translate import from_english, ENGLISH_LANGS
from app.pipeline.sarvam_tts import get_filler_audio, synthesize_streaming
from app.tools.registry import NOVA_TOOLS, execute_tool

logger = logging.getLogger(__name__)

_MANDI_KW = {
    'price', 'rate', 'mandi', 'market', 'cost',
    'tomato', 'onion', 'wheat', 'rice', 'potato', 'cotton',
    'maize', 'soybean', 'groundnut', 'sugarcane', 'chilli',
}
_WEATHER_KW = {
    'weather', 'rain', 'rainfall', 'forecast', 'temperature',
    'wind', 'storm', 'cloud', 'sunny', 'hot', 'cold', 'humid', 'monsoon',
}
_SCHEME_KW = {
    'scheme', 'subsidy', 'government', 'kisan', 'eligible', 'eligibility',
    'benefit', 'loan', 'insurance', 'fasal', 'yojana',
}
_QUESTION_WORDS = {'what', 'when', 'where', 'who', 'why', 'how', 'which', 'is', 'are', 'will', 'can', 'do', 'does'}


def _classify_filler(transcript: str) -> str:
    """Classify transcript into a filler category for context-aware audio selection."""
    words = transcript.lower().split()
    word_set = set(words)

    if word_set & _MANDI_KW:
        return 'mandi'
    if word_set & _WEATHER_KW:
        return 'weather'
    if word_set & _SCHEME_KW:
        return 'scheme'

    if len(words) <= 4 and '?' not in transcript and not (word_set & _QUESTION_WORDS):
        return 'none'

    return 'generic'


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


_SENTENCE_RE = re.compile(r'(?<=[.!?।])\s+')


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on . ! ? ।  Returns [text] if no split found."""
    parts = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
    return parts if parts else [text]


async def _translate_and_tts(
    sentence: str,
    detected_lang: str,
    is_english: bool,
    q: asyncio.Queue,
    sample_rate: int = 8000,
) -> None:
    """Translate one sentence and synthesize it.

    Puts (sample_rate, np.ndarray) chunks into q, then puts None sentinel.
    """
    try:
        text = sentence if is_english else await from_english(sentence, detected_lang)
        logger.info("[TTS] lang=%s text=%r", detected_lang, text[:80])
        chunk_count = 0
        async for chunk in synthesize_streaming(text, detected_lang, sample_rate=sample_rate):
            arr = np.frombuffer(chunk, dtype=np.int16).copy()
            await q.put((sample_rate, arr))
            chunk_count += 1
        logger.info("[TTS] done — %d chunks for lang=%s", chunk_count, detected_lang)
    except Exception:
        logger.exception("_translate_and_tts error for: %r", sentence)
    finally:
        await q.put(None)  # per-sentence sentinel — always emitted even on error


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

    # 2. Filler — classify transcript, play contextual audio (0ms, no API call)
    filler_category = _classify_filler(english_transcript)
    filler_audio = get_filler_audio(detected_lang, filler_category, sample_rate=8000)
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


async def process_turn_streaming(
    audio_bytes: bytes,
    farmer_profile: dict | None,
    conversation_history: list[dict],
    language_code: str,
    audio_queue: asyncio.Queue,
    sample_rate: int = 8000,
) -> tuple[str, str, str]:
    """Process one voice turn with sentence-level parallel TTS pipelining.

    Puts (sample_rate, np.ndarray) tuples into audio_queue as audio becomes available.
    Puts a final None sentinel when the turn is fully done.
    Returns (english_transcript, detected_lang, english_response).
    """
    if not audio_bytes:
        await audio_queue.put(None)
        return ("", language_code, "")

    is_english = language_code in ENGLISH_LANGS

    # 1. ASR
    asr_result = await transcribe(
        audio_bytes,
        language_code,
        mode="transcribe" if is_english else "translate",
    )
    transcript = asr_result["transcript"]
    detected_lang = asr_result["language_code"]
    logger.info("[ASR] input_lang=%s detected_lang=%s transcript=%r", language_code, detected_lang, transcript)

    if not transcript.strip():
        await audio_queue.put(None)
        return ("", detected_lang, "")

    is_english = detected_lang in ENGLISH_LANGS

    # 2. Filler — classify transcript, play contextual audio (0ms, no API call)
    filler_category = _classify_filler(transcript)
    filler = get_filler_audio(detected_lang, filler_category, sample_rate=sample_rate)
    if filler:
        arr = np.frombuffer(filler, dtype=np.int16).copy()
        await audio_queue.put((sample_rate, arr))

    # 3. Nova — non-streaming, handles tool calls correctly
    messages = list(conversation_history)
    messages.append({"role": "user", "content": [{"text": transcript}]})
    english_response = await nova_client.generate(
        user_text="",
        conversation_history=messages,
        tools=NOVA_TOOLS,
        tool_executor=execute_tool,
    )

    if not english_response or isinstance(english_response, dict):
        await audio_queue.put(None)
        return (transcript, detected_lang, "")

    english_response = _expand_numbers(english_response)

    # 4. Sentence-level parallel translate + TTS
    sentences = _split_sentences(english_response)

    # Each sentence gets its own queue — start all tasks simultaneously, drain in order
    sent_queues: list[asyncio.Queue] = [asyncio.Queue() for _ in sentences]
    tasks = [
        asyncio.create_task(
            _translate_and_tts(sent, detected_lang, is_english, sent_queues[i], sample_rate)
        )
        for i, sent in enumerate(sentences)
    ]

    try:
        # Drain each sentence queue in order; sentence N+1 may already be ready while N plays
        for q in sent_queues:
            while True:
                item = await q.get()
                if item is None:
                    break
                await audio_queue.put(item)
    finally:
        # Cancel any tasks still running (e.g. if this coroutine is cancelled on client disconnect)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    await audio_queue.put(None)   # turn-level sentinel
    return (transcript, detected_lang, english_response)
