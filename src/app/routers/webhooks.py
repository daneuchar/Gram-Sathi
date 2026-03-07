"""Twilio webhooks — missed call detection and SIP callback."""
import asyncio
import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import Response

from livekit.api import (
    LiveKitAPI,
    CreateRoomRequest,
    CreateSIPParticipantRequest,
    RoomAgentDispatch,
)

from app.config import settings
from app.sip_trunk import ensure_sip_trunk

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def _get_params(request: Request) -> dict:
    """Read params from form body (POST) or query string (GET)."""
    if request.method == "POST":
        form = await request.form()
        return dict(form)
    return dict(request.query_params)


@router.api_route("/missed-call", methods=["GET", "POST"])
async def missed_call(request: Request):
    """Handle incoming Twilio call — reject it, then call back via SIP.

    Twilio sends this webhook when a call comes in. We reject immediately
    (farmer pays nothing), then initiate a callback via LiveKit SIP.
    """
    params = await _get_params(request)
    from_number = params.get("From", "")
    call_sid = params.get("CallSid", "")

    logger.info("[missed-call] incoming from %s (CallSid=%s)", from_number, call_sid)

    if not from_number:
        logger.warning("[missed-call] no From number, ignoring")
        return Response(
            content='<?xml version="1.0"?><Response><Reject/></Response>',
            media_type="text/xml",
        )

    # Reject the call immediately — farmer pays nothing
    # Then trigger async callback
    asyncio.create_task(_callback_farmer(from_number))

    return Response(
        content='<?xml version="1.0"?><Response><Reject reason="busy"/></Response>',
        media_type="text/xml",
    )


async def _callback_farmer(phone: str) -> None:
    """Create a LiveKit room and dial the farmer back via SIP."""
    # Small delay so Twilio fully processes the rejected call
    await asyncio.sleep(2)

    room_name = f"gram-saathi-callback-{int(time.time())}"
    livekit_url = settings.livekit_url or "ws://localhost:7880"

    try:
        trunk_id = await ensure_sip_trunk()

        async with LiveKitAPI(
            url=livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        ) as api:
            # Create room with agent dispatch
            await api.room.create_room(CreateRoomRequest(
                name=room_name,
                empty_timeout=300,
                metadata=phone,  # Agent reads phone from room metadata
                agents=[RoomAgentDispatch(agent_name="")],
            ))
            logger.info("[callback] room created: %s", room_name)

            # Create SIP participant — LiveKit dials the farmer via Twilio
            sip_info = await api.sip.create_sip_participant(
                CreateSIPParticipantRequest(
                    sip_trunk_id=trunk_id,
                    sip_call_to=phone,
                    room_name=room_name,
                    participant_identity=f"phone-{phone}",
                    participant_name="Farmer",
                    participant_metadata=phone,
                    play_ringtone=True,
                    krisp_enabled=True,
                ),
            )
            logger.info("[callback] SIP participant created: %s → %s", sip_info.participant_id, phone)

    except Exception:
        logger.exception("[callback] failed to call back %s", phone)


@router.api_route("/call-status", methods=["GET", "POST"])
async def call_status(request: Request):
    """Twilio call status callback (optional, for logging)."""
    params = await _get_params(request)
    call_sid = params.get("CallSid", "")
    status = params.get("CallStatus", "")
    logger.info("[call-status] %s → %s", call_sid, status)
    return Response(content="<Response/>", media_type="text/xml")
