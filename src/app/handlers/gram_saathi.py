import asyncio
import io
import logging
import wave
from collections.abc import AsyncGenerator

import numpy as np
from fastrtc import ReplyOnPause

from app.pipeline.pipeline import process_turn_streaming

logger = logging.getLogger(__name__)

SAMPLE_RATE = 8000


def _ndarray_to_wav(sample_rate: int, audio: np.ndarray) -> bytes:
    """Convert a numpy int16 array to WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


async def _safe_process_turn_streaming(
    audio_bytes: bytes,
    farmer_profile,
    conversation_history: list[dict],
    language_code: str,
    audio_queue: asyncio.Queue,
    sample_rate: int,
) -> tuple[str, str, str]:
    """Wrapper that guarantees None sentinel is put even if pipeline raises."""
    try:
        return await process_turn_streaming(
            audio_bytes=audio_bytes,
            farmer_profile=farmer_profile,
            conversation_history=conversation_history,
            language_code=language_code,
            audio_queue=audio_queue,
            sample_rate=sample_rate,
        )
    except Exception:
        logger.exception("process_turn_streaming error")
        await audio_queue.put(None)
        return ("", language_code, "")


class GramSaathiHandler(ReplyOnPause):
    """Voice handler for Gram Saathi.

    ReplyOnPause runs Silero VAD on each incoming audio frame and calls
    _reply_fn only once per complete utterance (after a pause is detected).
    _reply_fn is an async generator that yields (sample_rate, ndarray) audio
    chunks back to the caller as they become available.
    """

    def __init__(self):
        super().__init__(
            fn=self._reply_fn,
            output_sample_rate=SAMPLE_RATE,
            can_interrupt=False,
        )
        self.conversation_history: list[dict] = []
        self.language_code = "hi-IN"

    def copy(self) -> "GramSaathiHandler":
        """Called by FastRTC for each new WebRTC/Twilio connection."""
        return GramSaathiHandler()

    async def _reply_fn(self, audio: tuple[int, np.ndarray]) -> AsyncGenerator:
        """Called once per full utterance (after Silero VAD detects a pause).

        Runs ASR → LLM → TTS pipeline and yields (sample_rate, ndarray) chunks.
        """
        sample_rate, arr = audio
        wav_bytes = _ndarray_to_wav(sample_rate, arr.reshape(-1))

        audio_queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(
            _safe_process_turn_streaming(
                audio_bytes=wav_bytes,
                farmer_profile=None,
                conversation_history=list(self.conversation_history[-20:]),
                language_code=self.language_code,
                audio_queue=audio_queue,
                sample_rate=SAMPLE_RATE,
            )
        )

        # Drain audio queue, yielding each chunk to FastRTC as it arrives
        while True:
            item = await audio_queue.get()
            if item is None:
                break
            yield item

        # After all audio is yielded, capture the turn result and update state
        transcript, detected_lang, english_response = await task
        if transcript:
            self.conversation_history.append(
                {"role": "user", "content": [{"text": transcript}]}
            )
            if english_response:
                self.conversation_history.append(
                    {"role": "assistant", "content": [{"text": english_response}]}
                )
            self.language_code = detected_lang
            logger.info("[%s] user: %s", detected_lang, transcript)
            logger.info("[%s] assistant: %s", detected_lang, english_response)
