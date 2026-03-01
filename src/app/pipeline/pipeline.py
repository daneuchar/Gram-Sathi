import logging
import re
from collections.abc import AsyncGenerator, Callable, Awaitable

from app.pipeline.nova_client import NovaClient
from app.pipeline.sarvam_asr import transcribe
from app.pipeline.sarvam_tts import synthesize

logger = logging.getLogger(__name__)

FILLER_PHRASES = {
    "hi-IN": "एक पल रुकिए...",
    "ta-IN": "ஒரு நிமிடம்...",
    "te-IN": "ఒక్క క్షణం...",
    "mr-IN": "एक क्षण थांबा...",
    "kn-IN": "ಒಂದು ಕ್ಷಣ...",
    "bn-IN": "এক মুহূর্ত...",
}

SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?।])\s*")

nova_client = NovaClient()


async def _stream_tts_sentences(
    text_stream: AsyncGenerator[str, None],
    language_code: str,
) -> AsyncGenerator[bytes, None]:
    """Accumulate streamed tokens, split on sentence boundaries, synthesize each."""
    buffer = ""
    async for token in text_stream:
        if isinstance(token, dict):
            # tool use block — skip TTS for tool calls
            continue
        buffer += token
        # Check for sentence boundaries
        parts = SENTENCE_BOUNDARY.split(buffer)
        if len(parts) > 1:
            # All but last are complete sentences
            for sentence in parts[:-1]:
                sentence = sentence.strip()
                if sentence:
                    audio = await synthesize(sentence, language_code)
                    yield audio
            buffer = parts[-1]

    # Flush remaining
    buffer = buffer.strip()
    if buffer:
        audio = await synthesize(buffer, language_code)
        yield audio


async def process_turn(
    audio_bytes: bytes,
    farmer_profile: dict | None,
    conversation_history: list[dict],
    language_code: str,
    tools: list[dict] | None = None,
    tool_executor: Callable | None = None,
    audio_send_callback: Callable[[bytes], Awaitable[None]] | None = None,
) -> tuple[str, str]:
    """Process one voice turn: ASR -> filler -> Nova -> streaming TTS.

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

    # 2. Filler phrase — play immediately while Nova thinks
    filler = FILLER_PHRASES.get(detected_lang)
    if filler and audio_send_callback:
        filler_audio = await synthesize(filler, detected_lang)
        await audio_send_callback(filler_audio)

    # 3. Build messages and stream Nova response
    messages = list(conversation_history)
    messages.append({"role": "user", "content": [{"text": transcript}]})

    text_stream = nova_client.generate_stream(messages, tools)

    # 4. Stream TTS sentence by sentence
    full_response_parts: list[str] = []

    async def _capturing_stream() -> AsyncGenerator[str, None]:
        async for token in text_stream:
            if isinstance(token, str):
                full_response_parts.append(token)
            yield token

    async for audio_chunk in _stream_tts_sentences(_capturing_stream(), detected_lang):
        if audio_send_callback:
            await audio_send_callback(audio_chunk)

    return (transcript, detected_lang)
