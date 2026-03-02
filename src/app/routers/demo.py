import asyncio
import base64
import io
import json
import logging
import math
import struct
import wave
from collections import deque

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pathlib import Path

from app.pipeline.pipeline import process_turn

logger = logging.getLogger(__name__)

router = APIRouter()
STATIC = Path(__file__).parent.parent / "static"

SAMPLE_RATE = 16000

# Browser sends 2048-sample chunks at 16kHz → 128ms per chunk
CHUNK_SAMPLES = 2048
CHUNK_MS = (CHUNK_SAMPLES / SAMPLE_RATE) * 1000  # ~128ms

# VAD thresholds (16-bit signed PCM, RMS range 0–32768)
# Quiet room ambient ≈ 100–400, normal speech ≈ 1000–8000
SPEECH_ENERGY    = 600   # above = user is speaking; tune based on VAD rms= logs
BARGE_IN_ENERGY  = 400   # user speech during bot playback → interrupt

SILENCE_END_SECS   = 0.8
SILENCE_END_CHUNKS = max(1, int(SILENCE_END_SECS * 1000 / CHUNK_MS))   # ~6 chunks

MAX_UTTERANCE_SECS   = 10
MAX_UTTERANCE_CHUNKS = int(MAX_UTTERANCE_SECS * 1000 / CHUNK_MS)        # ~78 chunks

MIN_SPEECH_CHUNKS = 3  # min speech chunks before processing (~400ms)

# Debounce: require N consecutive speech chunks before entering speech state.
# Prevents single-chunk noise spikes from triggering a turn.
# Pre-speech ring buffer preserves audio from confirmation window so start
# of utterance isn't lost.
SPEECH_CONFIRM_CHUNKS = 2  # ~256ms at 128ms/chunk


def pcm16_rms(pcm_bytes: bytes) -> float:
    """RMS energy of raw 16-bit little-endian signed PCM bytes."""
    n = len(pcm_bytes) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack(f"<{n}h", pcm_bytes[:n * 2])
    return math.sqrt(sum(s * s for s in samples) / n)


@router.get("/")
async def demo_page():
    return FileResponse(STATIC / "index.html")


@router.websocket("/ws/demo")
async def demo_ws(websocket: WebSocket):
    await websocket.accept()
    logger.info("Browser voice client connected")

    audio_buffer = bytearray()
    conversation_history: list[dict] = []
    language_code = "hi-IN"
    sample_rate = SAMPLE_RATE

    # VAD state
    in_speech          = False
    silence_chunks     = 0
    speech_chunk_count = 0
    speech_confirm     = 0                              # consecutive speech chunks seen
    pre_speech_buf: deque = deque(maxlen=SPEECH_CONFIRM_CHUNKS)  # ring buffer for pre-roll

    # Bot playback state
    bot_speaking = False
    current_task: asyncio.Task | None = None

    async def send_audio(pcm_bytes: bytes):
        nonlocal bot_speaking
        bot_speaking = True
        payload = base64.b64encode(pcm_bytes).decode()
        await websocket.send_json({"event": "media", "media": {"payload": payload}})

    async def run_turn(wav_bytes: bytes):
        nonlocal bot_speaking, language_code
        try:
            transcript, detected_lang, assistant_response = await process_turn(
                wav_bytes,
                farmer_profile=None,
                conversation_history=list(conversation_history),
                language_code=language_code,
                audio_send_callback=send_audio,
            )
            if transcript:
                conversation_history.append(
                    {"role": "user", "content": [{"text": transcript}]}
                )
                if assistant_response:
                    conversation_history.append(
                        {"role": "assistant", "content": [{"text": assistant_response}]}
                    )
                language_code = detected_lang
                await websocket.send_json({"event": "transcript", "text": transcript})
                logger.info("[%s] %s", detected_lang, transcript)
        except asyncio.CancelledError:
            logger.info("Turn interrupted by barge-in")
            raise
        finally:
            bot_speaking = False
            await websocket.send_json({"event": "done"})

    def vad_reset():
        nonlocal in_speech, silence_chunks, speech_chunk_count, speech_confirm
        in_speech = False
        silence_chunks = 0
        speech_chunk_count = 0
        speech_confirm = 0
        pre_speech_buf.clear()
        audio_buffer.clear()

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "start":
                sample_rate = msg.get("sample_rate", SAMPLE_RATE)
                language_code = msg.get("language_code", "hi-IN")
                audio_buffer.clear()
                logger.info("Call started: lang=%s sr=%d", language_code, sample_rate)

            elif event == "media":
                # While bot is speaking, discard mic input to prevent echo feedback
                if bot_speaking:
                    vad_reset()
                    continue

                pcm_chunk = base64.b64decode(msg["media"]["payload"])
                energy = pcm16_rms(pcm_chunk)

                # ── VAD state machine ────────────────────────────────────
                is_speech = energy > SPEECH_ENERGY

                if not in_speech:
                    pre_speech_buf.append(pcm_chunk)
                    if is_speech:
                        speech_confirm += 1
                        if speech_confirm >= SPEECH_CONFIRM_CHUNKS:
                            # Confirmed real speech — include pre-roll so we don't clip start
                            in_speech = True
                            silence_chunks = 0
                            speech_chunk_count = SPEECH_CONFIRM_CHUNKS
                            for chunk in pre_speech_buf:
                                audio_buffer.extend(chunk)
                            pre_speech_buf.clear()
                    else:
                        speech_confirm = 0  # noise blip — reset confirmation counter

                else:
                    audio_buffer.extend(pcm_chunk)

                    if is_speech:
                        silence_chunks = 0
                        speech_chunk_count += 1
                    else:
                        silence_chunks += 1

                    end_of_utterance = (
                        silence_chunks >= SILENCE_END_CHUNKS
                        and speech_chunk_count >= MIN_SPEECH_CHUNKS
                    )
                    force_process = (
                        speech_chunk_count + silence_chunks >= MAX_UTTERANCE_CHUNKS
                    )

                    if (end_of_utterance or force_process) and not (
                        current_task and not current_task.done()
                    ):
                        wav = _pcm_to_wav(bytes(audio_buffer), sample_rate)
                        logger.info(
                            "End of utterance (speech=%d chunks, silence=%d chunks)",
                            speech_chunk_count, silence_chunks,
                        )
                        vad_reset()
                        current_task = asyncio.create_task(run_turn(wav))

            elif event == "end_call":
                if current_task and not current_task.done():
                    current_task.cancel()
                logger.info("Call ended by user")
                break

    except WebSocketDisconnect:
        logger.info("Browser client disconnected")
        if current_task and not current_task.done():
            current_task.cancel()
    except Exception as e:
        logger.exception("demo_ws error: %s", e)


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()
