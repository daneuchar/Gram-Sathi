# Gram Sathi

**Voice AI assistant for Indian farmers — one missed call, zero cost.**

150M+ Indian farmers have no smartphone or internet. Gram Sathi bridges this gap: a farmer gives a missed call (₹0), gets an AI callback delivering live market prices, weather forecasts, government scheme eligibility, and crop advice — in their own language, on any phone.

## How It Works

```
Farmer gives missed call → Twilio rejects (free) → System calls back via SIP
→ Voice agent connects → Farmer speaks in their language → AI responds
```

1. **Missed Call Trigger** — Farmer dials a number, Twilio detects and rejects it (farmer pays nothing)
2. **SIP Callback** — Backend creates a LiveKit room, dials the farmer back via SIP trunk
3. **Voice Conversation** — Real-time STT → LLM reasoning → TTS pipeline, all in the farmer's language
4. **Smart Tools** — Agent calls live APIs for mandi prices, weather, scheme eligibility

## Features

- **11 Indian Languages** — Hindi, Tamil, Telugu, Kannada, Marathi, Bengali, Gujarati, Punjabi, Malayalam, Odia, English
- **Live Mandi Prices** — Real-time commodity prices from 1,266+ mandis via data.gov.in
- **Weather Forecasts** — 5-day hyperlocal forecasts with severe weather alerts
- **Government Schemes** — Eligibility matching against 45+ central and state schemes
- **Crop Advisory** — Season-aware, region-specific farming guidance based on current date and location
- **Progressive Profiling** — Builds farmer profile naturally through conversation (no forms)
- **Analytics Dashboard** — Real-time call monitoring, live transcripts, user profiles, and system health

## Architecture

Single EC2 deployment (t3.medium, ap-south-1 Mumbai) running Docker Compose:

| Service | Role |
|---------|------|
| **LiveKit Server** | WebRTC signaling, audio routing, VAD (Silero) |
| **LiveKit SIP** | Outbound SIP trunk via Twilio Elastic SIP |
| **Voice Agent** | LiveKit Agents SDK — STT/LLM/TTS voice pipeline |
| **FastAPI Backend** | Webhooks, dashboard API, translation |
| **Next.js Dashboard** | Admin UI — call history, live transcripts, analytics |
| **PostgreSQL** | Users, call logs, conversation transcripts |
| **Redis** | LiveKit state, API response caching |

### Voice Pipeline

```
Farmer speaks → LiveKit (VAD) → Sarvam STT (saaras:v3) → AWS Bedrock Nova Lite 2 (tool use)
→ Sarvam TTS (bulbul:v3, ishita voice) → LiveKit → Farmer hears
```

### External APIs

- **AWS Bedrock** — Nova Lite 2, Converse API with tool use
- **Sarvam AI** — STT (saaras:v3) and TTS (bulbul:v3) via WebSocket
- **data.gov.in** — Mandi commodity prices (30min cache)
- **Open-Meteo** — Weather forecasts (2hr cache, free)
- **AWS Translate** — Dashboard transcript translation
- **Twilio** — Phone number + Elastic SIP Trunk

## Quick Start

### Prerequisites

- Docker and Docker Compose
- AWS credentials (Bedrock, Translate)
- Sarvam AI API key
- Twilio account (phone number + SIP trunk)
- data.gov.in API key

### Setup

```bash
# Clone
git clone https://github.com/daneuchar/Gram-Sathi.git
cd Gram-Sathi

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Start all services
docker compose up -d

# Dashboard available at http://localhost:3000
# Backend API at http://localhost:8000
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `SARVAM_API_KEY` | Sarvam AI API key for STT/TTS |
| `AWS_ACCESS_KEY_ID` | AWS credentials for Bedrock + Translate |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials |
| `AWS_DEFAULT_REGION` | `ap-south-1` (Mumbai) |
| `DATA_GOV_API_KEY` | data.gov.in API key for mandi prices |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | Twilio phone number (e.g., +1234567890) |
| `TWILIO_SIP_DOMAIN` | Twilio Elastic SIP trunk domain |
| `LIVEKIT_API_KEY` | LiveKit API key |
| `LIVEKIT_API_SECRET` | LiveKit API secret |

## Project Structure

```
src/app/
├── livekit_agent.py        # Voice agent — STT/LLM/TTS pipeline, session lifecycle
├── prompts.py              # System + onboarding prompts, marker extraction
├── config.py               # Environment config (Pydantic Settings)
├── database.py             # Async SQLAlchemy session, user management
├── sip_trunk.py            # LiveKit SIP outbound trunk bootstrap
├── main.py                 # FastAPI app entry point
├── models/                 # SQLAlchemy models
│   ├── user.py             #   Farmer profiles
│   ├── call_log.py         #   Call metadata
│   └── conversation.py     #   Conversation turns
├── routers/
│   ├── dashboard.py        #   Dashboard API (stats, calls, users, analytics)
│   ├── webhooks.py         #   Twilio missed call + SIP callback
│   └── test_call.py        #   Browser-based voice test
├── tools/
│   ├── mandi.py            #   Mandi price lookup (data.gov.in)
│   ├── weather.py          #   Weather forecast (Open-Meteo)
│   ├── schemes.py          #   Government scheme eligibility
│   └── crop_advisory.py    #   Crop advisory tool
└── plugins/
    └── bedrock_llm.py      #   AWS Bedrock LLM plugin for LiveKit

frontend/                   # Next.js 16 dashboard
├── src/app/
│   ├── page.tsx            #   Overview (stats cards)
│   ├── call-history/       #   Call history + live transcript viewer
│   ├── live-monitor/       #   Active calls monitor
│   ├── user-profiles/      #   Farmer profiles
│   ├── analytics/          #   Charts and trends
│   └── system-health/      #   API health checks
└── src/lib/
    ├── queries.ts           #   TanStack Query hooks
    └── types.ts             #   TypeScript types

docs/
├── architecture.drawio     # Architecture diagrams (2 tabs: System + Missed Call Flow)
├── design.md               # Original design document
└── requirements.md         # Product requirements
```

## Dashboard

The Next.js dashboard provides:

- **Overview** — Today's calls, total farmers, average duration, active calls
- **Call History** — Filterable table with click-to-view transcripts (live polling for in-progress calls)
- **Live Monitor** — Real-time active call tracking with auto-refresh
- **User Profiles** — Farmer profiles with language, location, crops, land size
- **Analytics** — Language distribution, tool usage, call volume trends, top states
- **System Health** — API endpoint health checks

## License

MIT
