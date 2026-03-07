# Gram Saathi — Design Document

## Architecture Overview

```
         ┌─────────────────┐
         │  Farmer (Any     │
         │  Phone)          │
         └────────┬────────┘
                  │ Missed Call (₹0)
                  ▼
         ┌─────────────────┐
         │  Cloud Telephony │
         │  Provider        │
         │  - Missed Call   │
         │  - Callback API  │
         │  - WebSocket     │
         │    Audio Stream  │
         └────────┬────────┘
                  │ WebSocket (8kHz PCM)
                  ▼
┌─────────────────────────────────────────────┐
│         GRAM SATHI BACKEND                  │
│         FastAPI + Pipecat                   │
│                                             │
│  ┌───────────┐  ┌──────────┐  ┌──────────┐ │
│  │Sarvam ASR │→ │ Bedrock  │→ │Sarvam TTS│ │
│  │Speech→Text│  │ Claude   │  │Text→Speech│ │
│  │22 langs   │  │ AI Agent │  │Natural    │ │
│  └───────────┘  └────┬─────┘  └──────────┘ │
│                      │ Function Calls       │
│              ┌───────┴────────┐             │
│              │  Tool Executor │             │
│              └───────┬────────┘             │
│       ┌──────┬───────┼───────┬────────┐    │
│       ▼      ▼       ▼       ▼        │    │
│   ┌──────┐┌──────┐┌──────┐┌───────┐  │    │
│   │Mandi ││Weather││Govt  ││Crop   │  │    │
│   │Prices││Forcast││Scheme││Advisor│  │    │
│   └──┬───┘└──┬───┘└──┬───┘└───────┘  │    │
│      │       │       │                │    │
│  ┌───┴───────┴───┐ ┌─┴────────────┐  │    │
│  │ PostgreSQL    │ │ Redis Cache  │  │    │
│  │ Users, Calls  │ │ Prices,      │  │    │
│  │ Conversations │ │ Weather,     │  │    │
│  │ Alerts        │ │ Sessions     │  │    │
│  └───────────────┘ └──────────────┘  │    │
│                                       │    │
│  ┌───────────────────────────────┐   │    │
│  │ Streamlit Dashboard           │   │    │
│  │ Calls · Users · Analytics     │   │    │
│  └───────────────────────────────┘   │    │
└─────────────────────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
  ┌────────────┐ ┌────────────┐ ┌────────────┐
  │ Amazon     │ │ Amazon Q   │ │ External   │
  │ Bedrock    │ │ Business   │ │ APIs       │
  │ Claude LLM │ │ Scheme KB  │ │ data.gov.in│
  │ ap-south-1 │ │ 1000+      │ │ IndianAPI  │
  └────────────┘ └────────────┘ └────────────┘
```

## Core Call Flow

```
1. Farmer dials → Missed call (₹0, auto-disconnects)
2. Webhook fires → Backend logs call, creates/updates user profile
3. 5-second delay → Backend triggers outbound callback
4. Farmer answers → WebSocket audio stream opens
5. Voice loop begins:
   Farmer speaks → ASR → Claude (+ tool calls) → TTS → Farmer hears response
6. Farmer hangs up → Call logged, session cleaned up
```

## Component Design

### 1. Telephony Gateway

Handles all phone interactions via a cloud telephony provider.

| Endpoint | Purpose |
|----------|---------|
| `POST /webhooks/missed-call` | Receive missed call notification |
| `POST /webhooks/call-status` | Receive call status updates |
| `WS /ws/voice` | Bidirectional audio stream (8kHz PCM, base64 JSON) |

**Callback logic:** On missed call → wait 5 seconds → initiate outbound call → connect to voice pipeline via WebSocket.

### 2. Voice Pipeline (Pipecat)

Streaming producer-consumer architecture. All three stages run concurrently — not sequentially.

```
Audio In → [ASR] → transcript → [LLM] → tokens → [TTS] → Audio Out
                                  ↓
                            [Tool Calls]
                                  ↓
                            [Tool Results]
                                  ↓
                            [Continue LLM]
```

**ASR — Sarvam AI (Saaras v3):**
- Streaming WebSocket, auto language detection
- 8kHz PCM input matching telephony audio format
- High VAD sensitivity for noisy rural environments

**LLM — Amazon Bedrock Claude:**
- Converse Stream API with function calling
- System prompt includes farmer profile for personalization
- Tool use loop: call tools → feed results back → generate final response

**TTS — Sarvam AI (Bulbul v3):**
- Streaming WebSocket, sentence-level buffering
- PCM output at 8kHz matching telephony format
- Natural voices per language, pace set to 0.9 for rural clarity

**Latency optimizations:**
- Sentence-level TTS (don't wait for full response)
- Filler phrases while LLM processes ("Haan ji, dekh rahi hoon...")
- Persistent WebSocket connections (no reconnect per utterance)
- All AWS services in ap-south-1 (Mumbai) for minimum network hop

### 3. LLM Agent

Claude acts as a conversational agent with access to 4 tools.

**System prompt directives:**
- Keep responses under 3 short sentences (phone conversation)
- Respond in the same language the farmer speaks
- Always use tools for real data — never fabricate prices/weather/schemes
- Ask one question at a time if information is needed
- Progressively build farmer profile through natural conversation

**Tool definitions:**

| Tool | Input | Source | Cache TTL |
|------|-------|--------|-----------|
| `get_mandi_prices` | commodity, state, district | data.gov.in | 30 min |
| `get_weather_forecast` | district, state | IndianAPI.in | 2 hours |
| `check_scheme_eligibility` | farmer profile fields | Amazon Q Business | — |
| `get_crop_advisory` | crop, state, season | Static data + LLM | — |

**Tool execution flow:**
```
Claude decides tool is needed
  → Function call with args
    → Tool executor checks Redis cache
      → Cache hit: return cached data
      → Cache miss: call external API → cache result → return
    → Tool result fed back to Claude
      → Claude generates farmer-friendly response
```

### 4. Knowledge Base (Amazon Q Business)

- Ingests MyScheme.gov.in dataset (HuggingFace: `shrijayan/gov_myscheme`)
- 1,000+ central and state government schemes
- Indexed by: eligibility criteria, state, category, benefits
- Natural language query: "schemes for small farmer in UP growing wheat"
- Returns: scheme name, eligibility match, benefit amount, application process

### 5. Data Layer

**PostgreSQL — Persistent storage:**

```sql
users            → phone, name, state, district, crops, land_acres, language
call_logs        → call_sid, direction, status, duration, language, timestamps
conversation_turns → turn_number, transcript, tools_used, latency_ms
alert_queue      → user_id, alert_type, message, priority, status
mandi_prices     → commodity, state, district, prices, arrival_date
```

**Redis — Cache and sessions:**

| Key Pattern | Data | TTL |
|-------------|------|-----|
| `mandi:{commodity}:{state}:{district}` | Price JSON | 30 min |
| `weather:{district}:{state}` | Forecast JSON | 2 hours |
| `session:{call_id}` | Conversation state | 1 hour |
| `ratelimit:{phone}` | Call count | 24 hours |

### 6. Dashboard (Streamlit)

| Page | Data |
|------|------|
| Live Monitor | Active calls with real-time transcripts |
| Call History | Duration, language, topics, recording |
| User Profiles | Progressive farmer data |
| Analytics | Query distribution, language usage, tool utilization |
| System Health | API latency, error rates, service status |

**Endpoints:**

```
GET  /api/dashboard/calls       → Paginated call logs
GET  /api/dashboard/users       → User list with stats
GET  /api/dashboard/analytics   → Aggregated charts data
WS   /api/dashboard/live        → Real-time call updates
GET  /api/health                → Service health check
```

## Data Flow Diagram

```
┌──────────┐   missed call   ┌───────────┐  webhook  ┌──────────┐
│  Farmer  │ ───────────────→│ Telephony │ ────────→ │ FastAPI  │
│  Phone   │ ←───────────────│ Provider  │ ←──────── │ Backend  │
└──────────┘   voice call    └───────────┘  callback  └────┬─────┘
                                                           │
                              ┌─────────────────────────────┤
                              ▼                             ▼
                     ┌────────────────┐           ┌──────────────┐
                     │  Voice Pipeline│           │  Data Layer  │
                     │  ASR→LLM→TTS  │           │  PG + Redis  │
                     └───────┬────────┘           └──────────────┘
                             │
                    ┌────────┴────────┐
                    ▼        ▼        ▼
              ┌──────┐ ┌────────┐ ┌───────┐
              │Mandi │ │Weather │ │Schemes│
              │Prices│ │API     │ │Amazon │
              │data. │ │Indian  │ │Q Biz  │
              │gov.in│ │API.in  │ │       │
              └──────┘ └────────┘ └───────┘
```

## Security

- No user-facing authentication — farmers identified by phone number only
- All external API keys stored in environment variables, never in code
- Service authentication: API keys, Bearer tokens, AWS IAM SigV4
- Redis rate limiting prevents duplicate callbacks and abuse
- No PII stored beyond phone number and voluntarily shared profile data

## Deployment

```yaml
# docker-compose.yml
services:
  backend:    FastAPI app (port 8000)
  postgres:   PostgreSQL (port 5432)
  redis:      Redis (port 6379)
  dashboard:  Streamlit (port 8501)
```

**Production target:** AWS ap-south-1 (Mumbai) for minimum latency to Indian telephony and Bedrock services.
