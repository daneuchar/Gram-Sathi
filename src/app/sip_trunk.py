"""Bootstrap LiveKit SIP outbound trunk for Twilio."""
import logging

from livekit.api import (
    LiveKitAPI,
    CreateSIPOutboundTrunkRequest,
    ListSIPOutboundTrunkRequest,
    SIPOutboundTrunkInfo,
)

from app.config import settings

logger = logging.getLogger(__name__)

_trunk_id: str | None = None


async def ensure_sip_trunk() -> str:
    """Ensure a LiveKit SIP outbound trunk exists for Twilio. Returns trunk ID."""
    global _trunk_id
    if _trunk_id:
        return _trunk_id

    # If pre-configured, use it
    if settings.sip_outbound_trunk_id:
        _trunk_id = settings.sip_outbound_trunk_id
        logger.info("[sip] using pre-configured trunk: %s", _trunk_id)
        return _trunk_id

    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise RuntimeError("[sip] TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set for SIP trunk")

    livekit_url = settings.livekit_url or "ws://localhost:7880"

    async with LiveKitAPI(
        url=livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    ) as api:
        # Check if trunk already exists
        existing = await api.sip.list_outbound_trunk(ListSIPOutboundTrunkRequest())
        for trunk in existing.items:
            if trunk.name == "twilio-gramvaani":
                _trunk_id = trunk.sip_trunk_id
                logger.info("[sip] found existing trunk: %s", _trunk_id)
                return _trunk_id

        # Create new outbound trunk
        # Twilio SIP domain format: <account-sid>.pstn.twilio.com
        twilio_sip_address = f"{settings.twilio_account_sid}.pstn.twilio.com"

        result = await api.sip.create_outbound_trunk(
            CreateSIPOutboundTrunkRequest(
                trunk=SIPOutboundTrunkInfo(
                    name="twilio-gramvaani",
                    address=twilio_sip_address,
                    numbers=[settings.twilio_phone_number],
                    auth_username=settings.twilio_account_sid,
                    auth_password=settings.twilio_auth_token,
                )
            )
        )
        _trunk_id = result.sip_trunk_id
        logger.info("[sip] created outbound trunk: %s → %s", _trunk_id, twilio_sip_address)
        return _trunk_id
