# Twilio Missed Call + LiveKit SIP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When a farmer gives a missed call to the Twilio number, detect it via webhook and call them back through LiveKit SIP, connecting them to the Gram Saathi voice agent.

**Architecture:** Twilio receives the missed call and hits our webhook. Our backend rejects the call (TwiML `<Reject/>`), then creates a LiveKit room and SIP participant. LiveKit dials the farmer back via a pre-configured Twilio SIP outbound trunk. The agent joins the room automatically via dispatch — no agent code changes needed.

**Tech Stack:** Twilio webhooks, LiveKit SIP API (Python SDK), LiveKit server with SIP enabled, Docker Compose.

---

### Task 1: LiveKit Server SIP Configuration

**Files:**
- Create: `livekit.yaml`
- Modify: `docker-compose.yml`

**Step 1: Create LiveKit server config with SIP enabled**

Create `livekit.yaml`:

```yaml
port: 7880
rtc:
  port_range_start: 10000
  port_range_end: 20000
  use_external_ip: true
sip:
  port: 5060
keys:
  devkey: secret
```

**Step 2: Update docker-compose.yml — LiveKit service**

Replace the `livekit` service with:

```yaml
  livekit:
    image: livekit/livekit-server
    ports:
      - "7880:7880"
      - "7881:7881"
      - "7882:7882/udp"
      - "5060:5060/udp"
      - "5060:5060/tcp"
    volumes:
      - ./livekit.yaml:/etc/livekit.yaml
    command: --config /etc/livekit.yaml --node-ip ${PUBLIC_IP:-0.0.0.0} --bind 0.0.0.0
```

Note: Remove `--dev` flag since we now have an explicit config file. The `--dev` flag auto-generates keys; our config file specifies them explicitly.

**Step 3: Commit**

```bash
git add livekit.yaml docker-compose.yml
git commit -m "feat: add LiveKit SIP config and expose SIP ports"
```

---

### Task 2: Add SIP Trunk Config to Settings

**Files:**
- Modify: `src/app/config.py`

**Step 1: Add SIP trunk fields to Settings**

Add these fields to the `Settings` class in `src/app/config.py` after the existing Twilio section:

```python
    # SIP Trunk (for LiveKit → Twilio outbound calls)
    sip_outbound_trunk_id: str = ""  # Set after first trunk creation, avoids recreating
```

This is the only config we need. The Twilio SIP address is derived from the account SID. The trunk is created at startup via LiveKit API using the existing Twilio credentials.

**Step 2: Commit**

```bash
git add src/app/config.py
git commit -m "feat: add SIP outbound trunk ID to config"
```

---

### Task 3: SIP Trunk Bootstrap — Ensure Outbound Trunk Exists

**Files:**
- Create: `src/app/sip_trunk.py`

**Step 1: Create the SIP trunk bootstrap module**

Create `src/app/sip_trunk.py`:

```python
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
```

**Step 2: Commit**

```bash
git add src/app/sip_trunk.py
git commit -m "feat: add SIP trunk bootstrap for Twilio outbound calls"
```

---

### Task 4: Missed Call Webhook + SIP Callback

**Files:**
- Modify: `src/app/routers/webhooks.py`

**Step 1: Rewrite webhooks.py with missed call detection and SIP callback**

Replace the contents of `src/app/routers/webhooks.py`:

```python
"""Twilio webhooks — missed call detection and SIP callback."""
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
    import asyncio
    asyncio.create_task(_callback_farmer(from_number))

    return Response(
        content='<?xml version="1.0"?><Response><Reject reason="busy"/></Response>',
        media_type="text/xml",
    )


async def _callback_farmer(phone: str) -> None:
    """Create a LiveKit room and dial the farmer back via SIP."""
    import asyncio
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
```

**Step 2: Commit**

```bash
git add src/app/routers/webhooks.py
git commit -m "feat: missed call webhook with SIP callback via LiveKit"
```

---

### Task 5: Register Webhook Router in Main App

**Files:**
- Modify: `src/app/main.py`

**Step 1: Verify webhooks router is registered**

Read `src/app/main.py` and check if the webhooks router is already included. If not, add:

```python
from app.routers.webhooks import router as webhooks_router
app.include_router(webhooks_router)
```

**Step 2: Commit (if changed)**

```bash
git add src/app/main.py
git commit -m "feat: register webhooks router in FastAPI app"
```

---

### Task 6: SIP Setup Documentation

**Files:**
- Create: `docs/sip-setup.md`

**Step 1: Write the one-time setup guide**

Create `docs/sip-setup.md` with instructions for:

1. **Twilio Console** — configure phone number webhook URL to `https://gramsaathi.in/webhooks/missed-call`
2. **EC2 Security Group** — open ports 5060/UDP+TCP (SIP) and 10000-20000/UDP (RTP media)
3. **Deploy** — `docker compose up -d --build`
4. **Test** — call the Twilio number, hang up, wait for callback

**Step 2: Commit**

```bash
git add docs/sip-setup.md
git commit -m "docs: add one-time SIP trunk setup guide"
```

---

### Task 7: Deploy and Test

**Step 1: Copy files to server**

```bash
scp -i ~/.ssh/gramvaani_ec2 livekit.yaml ubuntu@gramsaathi.in:/tmp/
scp -i ~/.ssh/gramvaani_ec2 docker-compose.yml ubuntu@gramsaathi.in:/tmp/
scp -i ~/.ssh/gramvaani_ec2 src/app/sip_trunk.py ubuntu@gramsaathi.in:/tmp/
scp -i ~/.ssh/gramvaani_ec2 src/app/routers/webhooks.py ubuntu@gramsaathi.in:/tmp/
scp -i ~/.ssh/gramvaani_ec2 src/app/config.py ubuntu@gramsaathi.in:/tmp/

ssh -i ~/.ssh/gramvaani_ec2 ubuntu@gramsaathi.in "
  sudo cp /tmp/livekit.yaml /opt/gram-sathi/livekit.yaml
  sudo cp /tmp/docker-compose.yml /opt/gram-sathi/docker-compose.yml
  sudo cp /tmp/sip_trunk.py /opt/gram-sathi/src/app/sip_trunk.py
  sudo cp /tmp/webhooks.py /opt/gram-sathi/src/app/routers/webhooks.py
  sudo cp /tmp/config.py /opt/gram-sathi/src/app/config.py
"
```

**Step 2: Open SIP ports in EC2 security group**

User must add inbound rules:
- UDP 5060 from 0.0.0.0/0 (SIP signaling)
- TCP 5060 from 0.0.0.0/0 (SIP signaling)
- UDP 10000-20000 from 0.0.0.0/0 (RTP media)

**Step 3: Rebuild and restart**

```bash
ssh -i ~/.ssh/gramvaani_ec2 ubuntu@gramsaathi.in \
  "cd /opt/gram-sathi && sudo docker compose up -d --build"
```

**Step 4: Configure Twilio webhook**

In Twilio Console → Phone Numbers → select the number → Voice Configuration:
- "A call comes in" → Webhook → `https://gramsaathi.in/webhooks/missed-call` (POST)

**Step 5: Test**

Call the Twilio number from a phone, let it ring once, hang up. Within 3-5 seconds, you should receive a callback connected to the Gram Saathi agent.

**Step 6: Verify logs**

```bash
ssh -i ~/.ssh/gramvaani_ec2 ubuntu@gramsaathi.in \
  "cd /opt/gram-sathi && sudo docker compose logs --tail=50 backend agent"
```

Look for: `[missed-call] incoming from +91...` → `[callback] room created` → `[callback] SIP participant created`
