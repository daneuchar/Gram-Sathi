import asyncio
import io
import logging
import wave

import numpy as np
from fastrtc import AsyncStreamHandler

from app.pipeline.pipeline import process_turn_streaming

logger = logging.getLogger(__name__)

SAMPLE_RATE = 8000
FRAME_SIZE = 960  # ~120ms at 8kHz


def _ndarray_to_wav(sample_rate: int, audio: np.ndarray) -> bytes:
    """Convert a numpy int16 array to WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


class GramSaathiHandler(AsyncStreamHandler):
    """Single handler for both Twilio phone calls and browser WebRTC sessions.

    FastRTC handles:
    - Silero VAD: detects speech start/end, passes full utterance to receive()
    - Sample-rate conversion: Twilio 8kHz mulaw <-> handler's working rate
    - Sequential turn-taking via can_interrupt=False in the Stream config
    """

    def __init__(self):
        super().__init__(
            output_sample_rate=SAMPLE_RATE,
            output_frame_size=FRAME_SIZE,
        )
        self.conversation_history: list[dict] = []
        self.language_code = "hi-IN"
        self.audio_queue: asyncio.Queue = asyncio.Queue()

    async def receive(self, frame: tuple[int, np.ndarray]) -> None:
        """Called by FastRTC when a full utterance is ready (after VAD silence)."""
        sample_rate, audio = frame
        wav_bytes = _ndarray_to_wav(sample_rate, audio)
        asyncio.create_task(self._run_turn(wav_bytes))

    async def emit(self) -> tuple[int, np.ndarray] | None:
        """Called continuously by FastRTC — return next audio chunk or None."""
        try:
            item = await asyncio.wait_for(self.audio_queue.get(), timeout=0.02)
            return item  # either (sr, ndarray) or None sentinel — both acceptable to FastRTC
        except asyncio.TimeoutError:
            return None

    async def _run_turn(self, wav_bytes: bytes) -> None:
        try:
            transcript, detected_lang, assistant_response = await process_turn_streaming(
                audio_bytes=wav_bytes,
                farmer_profile=None,
                conversation_history=list(self.conversation_history[-20:]),
                language_code=self.language_code,
                audio_queue=self.audio_queue,
                sample_rate=SAMPLE_RATE,
            )
            if transcript:
                self.conversation_history.append(
                    {"role": "user", "content": [{"text": transcript}]}
                )
                if assistant_response:
                    self.conversation_history.append(
                        {"role": "assistant", "content": [{"text": assistant_response}]}
                    )
                self.language_code = detected_lang
                logger.info("[%s] user: %s", detected_lang, transcript)
                logger.info("[%s] assistant: %s", detected_lang, assistant_response)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("GramSaathiHandler._run_turn error")
            await self.audio_queue.put(None)  # ensure sentinel even on error
