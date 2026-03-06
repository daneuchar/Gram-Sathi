# Twilio Missed Call → LiveKit SIP Callback

## Overview

When a farmer gives a missed call to the Gram Saathi Twilio number, the system detects it and calls them back via LiveKit SIP, connecting them to the voice agent. The farmer pays nothing.

## Flow

```
Farmer dials Twilio number → rings 1-2 times → hangs up
    ↓
Twilio sends webhook to POST /webhooks/missed-call
(CallStatus = no-answer / busy / canceled, or duration <= 3s)
    ↓
Backend creates a LiveKit room + SIP participant
LiveKit dials farmer back via Twilio SIP trunk
    ↓
Farmer picks up → audio flows through LiveKit SIP → Agent joins room
    ↓
Normal Gram Saathi conversation
```

## Components

### 1. Twilio Phone Number Configuration (one-time)

- Point the incoming call webhook to `https://gramsaathi.in/webhooks/missed-call`
- TwiML response: `<Response><Reject/></Response>` or `<Response><Say>...</Say><Hangup/></Response>` after 1-2 rings
- Status callback URL: `https://gramsaathi.in/webhooks/call-status`

### 2. Twilio SIP Trunk (one-time)

- Create a SIP Trunk in Twilio console (Elastic SIP Trunking)
- Note the SIP domain: `<trunk-name>.pstn.twilio.com`
- Add Origination SIP URI pointing to LiveKit's SIP endpoint (EC2 public IP:5060)
- Add Termination credentials for outbound calls from LiveKit → Twilio

### 3. LiveKit SIP Configuration

**Server config (`livekit.yaml`):**
- Enable SIP with `sip: {}` in config
- Expose ports: 5060/UDP (SIP signaling), 10000-20000/UDP (RTP media)

**SIP Outbound Trunk (created via LiveKit API at startup):**
- Trunk config includes Twilio SIP domain, credentials
- Used by LiveKit to route outbound calls through Twilio

### 4. Backend: Missed Call Webhook

**Endpoint:** `POST /webhooks/missed-call`

Logic:
1. Receive Twilio webhook with `From`, `CallStatus`, `CallDuration`
2. Detect missed call: status in (no-answer, busy, canceled) OR duration <= 3
3. Extract farmer phone number
4. Create LiveKit room via API
5. Create SIP participant in that room — LiveKit dials the farmer via Twilio SIP trunk
6. Agent auto-joins via dispatch (existing behavior)

### 5. No Agent Changes

`livekit_agent.py` already reads phone from room metadata. SIP participants appear as regular participants in the room. No code changes needed.

## Files to Create/Modify

| File | Change |
|------|--------|
| `docker-compose.yml` | LiveKit SIP config, expose SIP/RTP ports |
| `livekit.yaml` | LiveKit server config with SIP enabled |
| `src/app/routers/webhooks.py` | Missed call detection + LiveKit SIP participant creation |
| `src/app/config.py` | Add SIP trunk config fields if needed |
| `docs/sip-setup.md` | One-time Twilio + LiveKit SIP trunk setup guide |

## What We Don't Need

- No Twilio Media Streams or custom WebSocket bridge
- No changes to STT/TTS pipeline
- No changes to `livekit_agent.py`
- No changes to frontend/test page
