import base64
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.pipeline.pipeline import process_turn

logger = logging.getLogger(__name__)

router = APIRouter()

BUFFER_THRESHOLD = 32000  # bytes


@router.websocket("/ws/voice/{call_sid}")
async def voice_ws(websocket: WebSocket, call_sid: str):
    await websocket.accept()
    logger.info("WebSocket connected: call_sid=%s", call_sid)

    audio_buffer = bytearray()
    conversation_history: list[dict] = []
    language_code = "hi-IN"

    async def audio_send_callback(audio_bytes: bytes):
        payload = base64.b64encode(audio_bytes).decode()
        await websocket.send_json({
            "event": "media",
            "media": {"payload": payload},
        })

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "media":
                chunk = base64.b64decode(msg["media"]["payload"])
                audio_buffer.extend(chunk)

                if len(audio_buffer) >= BUFFER_THRESHOLD:
                    transcript, detected_lang = await process_turn(
                        bytes(audio_buffer),
                        farmer_profile=None,
                        conversation_history=conversation_history,
                        language_code=language_code,
                        audio_send_callback=audio_send_callback,
                    )
                    if transcript:
                        conversation_history.append(
                            {"role": "user", "content": [{"text": transcript}]}
                        )
                        language_code = detected_lang
                    audio_buffer.clear()

            elif event == "stop":
                if audio_buffer:
                    transcript, detected_lang = await process_turn(
                        bytes(audio_buffer),
                        farmer_profile=None,
                        conversation_history=conversation_history,
                        language_code=language_code,
                        audio_send_callback=audio_send_callback,
                    )
                    if transcript:
                        conversation_history.append(
                            {"role": "user", "content": [{"text": transcript}]}
                        )
                    audio_buffer.clear()

                await websocket.send_json({"event": "stop"})
                break

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: call_sid=%s", call_sid)
