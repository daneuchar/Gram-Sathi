import asyncio
import audioop
import base64
import io
import json
import logging
import wave
from collections import deque

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.pipeline.pipeline import process_turn

logger = logging.getLogger(__name__)

router = APIRouter()

SAMPLE_RATE = 8000

# Twilio sends 20ms mulaw chunks (160 bytes each).
CHUNK_MS = 20
CHUNK_BYTES = int(SAMPLE_RATE * CHUNK_MS / 1000)  # 160 bytes

# VAD: RMS thresholds (mulaw → PCM energy)
SPEECH_ENERGY = 800    # above = speech; tune up if background noise triggers false starts
BARGE_IN_ENERGY = 200  # during bot playback, above = user interrupting

# Silence after speech ends the utterance
SILENCE_END_SECS = 0.8
SILENCE_END_CHUNKS = int(SILENCE_END_SECS * 1000 / CHUNK_MS)  # 40 chunks

# Safety cap — process even if silence hasn't been detected
MAX_UTTERANCE_SECS = 10
MAX_UTTERANCE_CHUNKS = int(MAX_UTTERANCE_SECS * 1000 / CHUNK_MS)  # 500 chunks

# Minimum speech before triggering (avoids processing tiny clicks/pops)
MIN_SPEECH_CHUNKS = 5  # 100ms

# Debounce: require N consecutive speech chunks before entering speech state.
SPEECH_CONFIRM_CHUNKS = 4  # 4 × 20ms = 80ms confirmation window

MAX_HISTORY = 20  # keep last 10 user+assistant turn pairs


def mulaw_to_wav(mulaw_bytes: bytes) -> bytes:
    pcm = audioop.ulaw2lin(mulaw_bytes, 2)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)
    return buf.getvalue()


def pcm_to_mulaw(pcm_bytes: bytes) -> bytes:
    return audioop.lin2ulaw(pcm_bytes, 2)


def chunk_rms(mulaw_bytes: bytes) -> float:
    pcm = audioop.ulaw2lin(mulaw_bytes, 2)
    return audioop.rms(pcm, 2)


@router.websocket("/ws/voice")
async def voice_ws(websocket: WebSocket):
    await websocket.accept()

    audio_buffer = bytearray()
    conversation_history: list[dict] = []
    language_code = "hi-IN"
    stream_sid: str | None = None
    call_sid: str | None = None

    # VAD state
    in_speech          = False
    silence_chunks     = 0
    speech_chunk_count = 0
    speech_confirm     = 0
    pre_speech_buf: deque = deque(maxlen=SPEECH_CONFIRM_CHUNKS)

    # Bot playback state
    bot_speaking = False
    current_task: asyncio.Task | None = None

    async def send_clear():
        if stream_sid:
            await websocket.send_json({"event": "clear", "streamSid": stream_sid})

    async def audio_send_callback(pcm_bytes: bytes):
        nonlocal bot_speaking
        bot_speaking = True
        mulaw = pcm_to_mulaw(pcm_bytes)
        payload = base64.b64encode(mulaw).decode()
        msg: dict = {"event": "media", "media": {"payload": payload}}
        if stream_sid:
            msg["streamSid"] = stream_sid
        await websocket.send_json(msg)

    async def run_turn(wav_bytes: bytes):
        nonlocal bot_speaking, language_code
        try:
            transcript, detected_lang, assistant_response = await process_turn(
                wav_bytes,
                farmer_profile=None,
                conversation_history=list(conversation_history[-MAX_HISTORY:]),
                language_code=language_code,
                audio_send_callback=audio_send_callback,
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
                logger.info("[%s] %s", detected_lang, transcript)
        except asyncio.CancelledError:
            logger.info("Turn interrupted by barge-in")
            raise
        finally:
            bot_speaking = False

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

            if event == "connected":
                logger.info("Twilio stream connected")

            elif event == "start":
                start = msg.get("start", {})
                stream_sid = msg.get("streamSid") or start.get("streamSid")
                call_sid = start.get("callSid")
                logger.info("Stream started: call_sid=%s streamSid=%s", call_sid, stream_sid)

            elif event == "media":
                mulaw_chunk = base64.b64decode(msg["media"]["payload"])
                energy = chunk_rms(mulaw_chunk)

                # ── Barge-in: user speaks while bot is playing ──────────────
                if bot_speaking and current_task and not current_task.done():
                    if energy > BARGE_IN_ENERGY:
                        logger.info("Barge-in detected (rms=%.0f) — interrupting bot", energy)
                        current_task.cancel()
                        await send_clear()
                        vad_reset()

                # ── VAD state machine ─────────────────────────────────────
                is_speech = energy > SPEECH_ENERGY

                if not in_speech:
                    pre_speech_buf.append(mulaw_chunk)
                    if is_speech:
                        speech_confirm += 1
                        if speech_confirm >= SPEECH_CONFIRM_CHUNKS:
                            in_speech = True
                            silence_chunks = 0
                            speech_chunk_count = SPEECH_CONFIRM_CHUNKS
                            for chunk in pre_speech_buf:
                                audio_buffer.extend(chunk)
                            pre_speech_buf.clear()
                    else:
                        speech_confirm = 0  # noise blip — reset

                else:
                    # Already in speech — buffer everything
                    audio_buffer.extend(mulaw_chunk)

                    if is_speech:
                        silence_chunks = 0
                        speech_chunk_count += 1
                    else:
                        silence_chunks += 1

                    # End of utterance: enough silence after enough speech
                    end_of_utterance = (
                        silence_chunks >= SILENCE_END_CHUNKS
                        and speech_chunk_count >= MIN_SPEECH_CHUNKS
                    )
                    # Safety cap: force process if utterance is too long
                    force_process = speech_chunk_count + silence_chunks >= MAX_UTTERANCE_CHUNKS

                    if (end_of_utterance or force_process) and not (
                        current_task and not current_task.done()
                    ):
                        wav = mulaw_to_wav(bytes(audio_buffer))
                        logger.info(
                            "End of utterance detected (speech=%d chunks, silence=%d chunks)",
                            speech_chunk_count, silence_chunks,
                        )
                        vad_reset()
                        current_task = asyncio.create_task(run_turn(wav))

            elif event == "stop":
                logger.info("Stream stopped: call_sid=%s", call_sid)
                if current_task and not current_task.done():
                    current_task.cancel()
                # Process any remaining buffered speech
                if audio_buffer and speech_chunk_count >= MIN_SPEECH_CHUNKS:
                    wav = mulaw_to_wav(bytes(audio_buffer))
                    audio_buffer.clear()
                    await run_turn(wav)
                break

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: call_sid=%s", call_sid)
        if current_task and not current_task.done():
            current_task.cancel()
    except Exception as e:
        logger.exception("voice_ws error: %s", e)
