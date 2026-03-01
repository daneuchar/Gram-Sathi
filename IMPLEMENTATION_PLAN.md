# Gram Sathi - Complete Implementation Plan

> **Hackathon:** Hack2Skill "AI for Bharat" (Rs 40L prizes)
> **Idea:** Zero-internet AI service for rural India via missed calls and voice callbacks
> **Requirements:** Must use Amazon Bedrock, Amazon Q, and Kiro

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Technology Choices](#2-technology-choices)
3. [Project Structure](#3-project-structure)
4. [Core Call Flow](#4-core-call-flow)
5. [Telephony Layer - Exotel](#5-telephony-layer---exotel)
6. [Voice Pipeline - Streaming ASR/LLM/TTS](#6-voice-pipeline---streaming-asrllmtts)
7. [LLM Agent - Bedrock Claude](#7-llm-agent---bedrock-claude)
8. [Knowledge Base - Amazon Q](#8-knowledge-base---amazon-q)
9. [Tool Implementations](#9-tool-implementations)
10. [Database Schema](#10-database-schema)
11. [Frontend Dashboard](#11-frontend-dashboard)
12. [Proactive Alerts System](#12-proactive-alerts-system)
13. [Build Sequence](#13-build-sequence)
14. [Demo Strategy](#14-demo-strategy)
15. [Environment Variables](#15-environment-variables)
16. [Dependencies](#16-dependencies)
17. [Risks and Mitigations](#17-risks-and-mitigations)
18. [API Reference Links](#18-api-reference-links)

---

## 1. Architecture Overview

```
                          RURAL FARMER
                     (Feature phone / any phone)
                              |
                         [Missed Call]
                              |
                    +---------v-----------+
                    |   EXOTEL PLATFORM   |
                    |  (Cloud Telephony)  |
                    |                     |
                    |  ExoPhone Number    |
                    |  Missed Call Detect |
                    |  Outbound Call API  |
                    |  WebSocket Stream   |
                    +---------+-----------+
                              |
                     WebSocket (wss://)
                     8kHz PCM audio
                              |
              +---------------v------------------+
              |      GRAM SATHI BACKEND          |
              |      (FastAPI + Python)           |
              |                                  |
              |  +----------------------------+  |
              |  |   Telephony Gateway        |  |
              |  |   - Exotel WebSocket Srv   |  |
              |  |   - Missed Call Webhook    |  |
              |  |   - Outbound Call Manager  |  |
              |  +-------------+--------------+  |
              |                |                 |
              |  +-------------v--------------+  |
              |  |   Voice Pipeline           |  |
              |  |   (Streaming Producer-     |  |
              |  |    Consumer Pattern)       |  |
              |  |                            |  |
              |  |  Exotel Audio              |  |
              |  |    -> Sarvam ASR (WS)      |  |
              |  |      -> Bedrock Claude     |  |
              |  |        (Converse Stream)   |  |
              |  |          -> Sarvam TTS (WS)|  |
              |  |            -> Exotel Audio  |  |
              |  +-------------+--------------+  |
              |                |                 |
              |  +-------------v--------------+  |
              |  |   LLM Agent Layer          |  |
              |  |   - Bedrock Claude         |  |
              |  |   - Tool Definitions       |  |
              |  |   - Conversation Memory    |  |
              |  +-------------+--------------+  |
              |                |                 |
              |  +-------------v--------------+  |
              |  |   Tool Execution Layer     |  |
              |  |   - Mandi Price Lookup     |  |
              |  |   - Weather Forecast       |  |
              |  |   - Scheme Eligibility     |  |
              |  |   - PM-KISAN Status        |  |
              |  |   - Crop Advisory          |  |
              |  +-------------+--------------+  |
              |                |                 |
              |  +-------------v--------------+  |
              |  |   Data Layer               |  |
              |  |   - PostgreSQL             |  |
              |  |   - Redis (cache + queue)  |  |
              |  +----------------------------+  |
              |                                  |
              |  +----------------------------+  |
              |  |   Proactive Alert Engine   |  |
              |  |   - APScheduler            |  |
              |  |   - Weather monitor        |  |
              |  |   - Price spike detector   |  |
              |  +----------------------------+  |
              |                                  |
              |  +----------------------------+  |
              |  |   Dashboard (Streamlit)    |  |
              |  |   - Call logs              |  |
              |  |   - User analytics         |  |
              |  |   - Query insights         |  |
              |  +----------------------------+  |
              +----------------------------------+
                              |
            +-----------------+------------------+
            |                 |                  |
    +-------v------+  +------v-------+  +-------v--------+
    | Amazon       |  | Amazon Q     |  | External APIs  |
    | Bedrock      |  | Business     |  |                |
    | (ap-south-1) |  | (Scheme KB)  |  | - data.gov.in  |
    |              |  |              |  | - IMD Weather  |
    | Claude       |  | MyScheme     |  | - eNAM Prices  |
    | Converse API |  | HuggingFace  |  | - Bhashini     |
    |              |  | dataset      |  |   (fallback)   |
    +--------------+  +--------------+  +----------------+
```

---

## 2. Technology Choices

| Component | Choice | Why | Cost |
|-----------|--------|-----|------|
| **Telephony** | Exotel | Indian provider, missed call API, WebSocket audio streaming, Pipecat integration | ₹1000 free trial |
| **ASR** | Sarvam AI (Saaras v3) | Sub-1s latency, 22 Indian languages, streaming WebSocket, auto-language detection | ₹1000 free credits (₹30/hr) |
| **TTS** | Sarvam AI (Bulbul v3) | 11 languages, 30+ voices, streaming WebSocket, PCM output matches Exotel | Included in credits (₹15-30/10K chars) |
| **LLM** | Amazon Bedrock Claude (ap-south-1) | Hackathon requirement, function calling, streaming Converse API | Pay-per-token |
| **Knowledge Base** | Amazon Q Business | Hackathon requirement, ingest MyScheme.gov.in for scheme matching | AWS pricing |
| **Mandi Prices** | data.gov.in API | Daily commodity prices from eNAM/AGMARKNET | Free with API key |
| **Weather** | IndianAPI.in | No IP whitelisting needed (unlike IMD official API) | Free 1000 requests |
| **Voice Framework** | Pipecat | Open-source pipeline framework with native Exotel serializer | Free |
| **Backend** | FastAPI + Python | Async WebSocket support, AI ecosystem | Free |
| **Database** | PostgreSQL + Redis | User profiles, call logs, caching | Free (Docker) |
| **Dashboard** | Streamlit | Rapid development for hackathon | Free |
| **IDE** | Kiro | Hackathon requirement, spec-driven development | Free |

### Why Exotel over Twilio?

Twilio does **not** support India region well. Exotel is the recommended alternative:

| Feature | Exotel | Twilio | Plivo |
|---------|--------|--------|-------|
| India numbers | Native | Limited | Available |
| Missed call API | Full support | N/A for India | Callbacks |
| WebSocket audio streaming | Yes | Yes | Yes |
| Pipecat integration | Native serializer | Native | No |
| Free trial | ₹1000 credits | $15 | Self-service |
| IVR webhook logic | Yes (App Bazaar) | TwiML | XML |
| Price (India calls) | Competitive | Expensive | $0.05/min |

**Other alternatives considered:** Knowlarity (no public pricing), Ozonetel (limited docs), MSG91 (basic IVR), FreeSWITCH+SIP (too complex for hackathon).

### Why Sarvam AI over Bhashini?

| Feature | Sarvam AI | Bhashini |
|---------|-----------|----------|
| Latency | <1 second | Not documented |
| Streaming API | WebSocket (mature) | WebSocket (newer) |
| Documentation | Excellent | Moderate |
| Languages (ASR) | 22 | 22 |
| Languages (TTS) | 11 | 22 |
| Auto language detect | Yes (Saaras v3) | No |
| Free tier | ₹1000 credits | Fully free |
| SDK | Python + JS | REST only |

**Strategy:** Use Sarvam AI as primary (better latency + docs), Bhashini as fallback (free + more TTS languages).

---

## 3. Project Structure

```
gramvaani/
├── .kiro/                          # Kiro IDE specs (hackathon requirement)
│   └── specs/
│       ├── voice-pipeline.md
│       ├── telephony.md
│       └── agent-tools.md
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI entry point
│   │   ├── config.py               # Settings via pydantic-settings
│   │   │
│   │   ├── telephony/
│   │   │   ├── __init__.py
│   │   │   ├── exotel_webhook.py   # Missed call webhook handler
│   │   │   ├── exotel_caller.py    # Outbound call API client
│   │   │   └── websocket_server.py # WebSocket endpoint for Exotel audio
│   │   │
│   │   ├── voice/
│   │   │   ├── __init__.py
│   │   │   ├── pipeline.py         # Pipecat pipeline orchestration
│   │   │   ├── sarvam_asr.py       # Sarvam streaming ASR service
│   │   │   ├── sarvam_tts.py       # Sarvam streaming TTS service
│   │   │   ├── bhashini_asr.py     # Bhashini ASR fallback
│   │   │   └── bhashini_tts.py     # Bhashini TTS fallback
│   │   │
│   │   ├── agent/
│   │   │   ├── __init__.py
│   │   │   ├── bedrock_agent.py    # Bedrock Converse API client
│   │   │   ├── tools.py            # Tool definitions (JSON Schema)
│   │   │   ├── tool_executor.py    # Tool dispatch + execution
│   │   │   ├── prompts.py          # System prompts (multilingual)
│   │   │   └── conversation.py     # Conversation state management
│   │   │
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── mandi_prices.py     # data.gov.in price lookup
│   │   │   ├── weather.py          # IndianAPI.in weather forecast
│   │   │   ├── scheme_matcher.py   # Amazon Q scheme eligibility
│   │   │   ├── pm_kisan.py         # PM-KISAN status check
│   │   │   └── crop_advisory.py    # Crop advice engine
│   │   │
│   │   ├── knowledge/
│   │   │   ├── __init__.py
│   │   │   ├── amazon_q_client.py  # Amazon Q Business integration
│   │   │   ├── scheme_loader.py    # Load MyScheme HuggingFace data
│   │   │   └── scheme_index.py     # Local scheme search (fallback)
│   │   │
│   │   ├── data/
│   │   │   ├── __init__.py
│   │   │   ├── database.py         # SQLAlchemy async engine
│   │   │   ├── models.py           # ORM models
│   │   │   ├── schemas.py          # Pydantic schemas
│   │   │   ├── crud.py             # CRUD operations
│   │   │   └── cache.py            # Redis caching layer
│   │   │
│   │   ├── alerts/
│   │   │   ├── __init__.py
│   │   │   ├── scheduler.py        # APScheduler for proactive calls
│   │   │   ├── weather_monitor.py  # Weather alert detection
│   │   │   ├── price_monitor.py    # Price spike detection
│   │   │   └── alert_caller.py     # Outbound alert call trigger
│   │   │
│   │   └── api/
│   │       ├── __init__.py
│   │       ├── routes.py           # REST API routes
│   │       ├── dashboard.py        # Dashboard data endpoints
│   │       └── health.py           # Health check
│   │
│   ├── alembic/                    # Database migrations
│   │   ├── versions/
│   │   └── env.py
│   │
│   ├── tests/
│   │   ├── test_telephony.py
│   │   ├── test_voice_pipeline.py
│   │   ├── test_agent.py
│   │   └── test_tools.py
│   │
│   ├── data/
│   │   ├── schemes/                # Cached MyScheme data (JSON)
│   │   ├── crops/                  # Crop advisory knowledge base
│   │   └── prompts/                # System prompt templates
│   │
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── dashboard/                      # Streamlit dashboard
│   ├── app.py
│   ├── pages/
│   │   ├── call_logs.py
│   │   ├── users.py
│   │   ├── analytics.py
│   │   └── alerts.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── infra/
│   ├── docker-compose.yml          # Local dev: Postgres + Redis
│   └── cdk/                        # AWS CDK for Bedrock/Q setup
│
├── scripts/
│   ├── seed_schemes.py             # Load MyScheme from HuggingFace
│   ├── test_call.py                # Trigger a test outbound call
│   └── benchmark_latency.py        # Measure pipeline latency
│
├── docs/
│   ├── architecture.md
│   └── demo-runbook.md
│
├── IMPLEMENTATION_PLAN.md          # This file
├── README.md
├── Makefile
└── .env.example
```

---

## 4. Core Call Flow

### Step-by-Step: Missed Call -> Callback -> Voice AI

```
1. Farmer gives missed call to ExoPhone number
   └── Call auto-disconnects (FREE for farmer)

2. Exotel fires webhook POST to /webhooks/exotel/missed-call
   └── Payload: CallSid, From (farmer number), To (ExoPhone), Status

3. Backend processes webhook:
   ├── Look up or create user profile from phone number
   ├── Log the missed call in database
   └── Schedule callback after 5-second delay (avoid calling while hanging up)

4. Backend triggers outbound call via Exotel API
   └── POST /v1/Accounts/{sid}/Calls/connect
       ├── From: farmer's number
       ├── CallerId: ExoPhone number
       └── Url: Voicebot App Bazaar flow

5. Farmer answers the callback
   └── Exotel Voicebot applet opens WebSocket to /ws/voice
       └── Streams 8kHz, 16-bit, mono PCM audio (base64 in JSON)

6. Voice Pipeline activates:
   ├── Greeting: "Namaste! Main Gram Sathi hoon. Aap kya jaanna chahte hain?"
   └── Loop:
       ├── Exotel audio -> Sarvam ASR (streaming WebSocket)
       ├── ASR transcript -> Bedrock Claude (Converse Stream + tools)
       ├── Claude response -> Sarvam TTS (streaming WebSocket)
       └── TTS audio -> Exotel -> Farmer's phone

7. During conversation:
   ├── Claude uses tools to fetch real data (prices, weather, schemes)
   ├── User profile is progressively updated (state, crops, etc.)
   └── Each turn is logged (transcript, tools used, latency)

8. Farmer hangs up
   └── Call log finalized, session cleaned up
```

### Streaming Pipeline (Concurrent, NOT Sequential)

```
┌──────────────┐   partial    ┌──────────────┐   tokens    ┌──────────────┐
│  Sarvam ASR  │──transcripts──>│ Bedrock Claude│──stream────>│  Sarvam TTS  │
│  (WebSocket) │              │ (Converse)   │            │  (WebSocket) │
└──────┬───────┘              └──────┬───────┘            └──────┬───────┘
       │                             │                           │
  audio chunks                  tool calls                  audio chunks
  from Exotel                  (async exec)                to Exotel
```

**Target latency:** <1.5 seconds from end-of-speech to first audio response

**Optimizations:**
- Sentence-level TTS: buffer LLM tokens until `.` or `?`, send to TTS immediately
- Pre-buffered filler phrases: "Haan ji, main dekh rahi hoon..." while LLM processes
- Persistent WebSocket connections to Sarvam (no reconnect per utterance)
- All AWS services in ap-south-1 (Mumbai) for minimum network latency
- Connection pooling for Bedrock API calls

---

## 5. Telephony Layer - Exotel

### 5A. Account Setup

1. Sign up at [exotel.com](https://exotel.com) -- get ₹1000 free trial credits
2. Get an ExoPhone number (Indian virtual number)
3. In App Bazaar, create a flow:
   - Incoming call -> Passthru applet (async, points to our missed call webhook)
   - The flow intentionally does NOT answer (so the call is free for the farmer)
4. Create a second flow for the Voicebot:
   - Voicebot applet configured to connect WebSocket to our server
5. Note down: Account SID, API Key, API Token, ExoPhone number, Voicebot App ID

### 5B. Missed Call Webhook

```python
# /app/telephony/exotel_webhook.py

@router.post("/webhooks/exotel/missed-call")
async def handle_missed_call(request: Request):
    form_data = await request.form()
    caller_number = form_data.get("From")
    call_sid = form_data.get("CallSid")

    # Look up or create user
    user = await get_or_create_user(caller_number)

    # Log the missed call
    await log_call(call_sid, caller_number, call_type="missed_call")

    # Schedule callback (5s delay)
    await schedule_callback(caller_number, user.id, delay_seconds=5)

    return {"status": "ok"}
```

### 5C. Outbound Callback

```python
# /app/telephony/exotel_caller.py

class ExotelCaller:
    BASE_URL = "https://api.in.exotel.com"

    async def initiate_callback(self, to_number: str, user_id: str):
        endpoint = f"{self.BASE_URL}/v1/Accounts/{self.account_sid}/Calls/connect"
        payload = {
            "From": to_number,
            "CallerId": self.exophone,
            "CallType": "trans",
            "Url": f"http://my.exotel.in/exoml/start/{self.voicebot_app_id}",
            "StatusCallback": f"{self.server_url}/webhooks/exotel/call-status",
            "StatusCallbackContentType": "application/json",
            "Record": "true",
            "CustomField": user_id,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                endpoint, data=payload,
                auth=(self.api_key, self.api_token),
            )
        return response.json()
```

### 5D. WebSocket Audio Server

```python
# /app/telephony/websocket_server.py

@app.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket):
    await websocket.accept()

    # Parse Exotel metadata from initial messages
    call_data = await parse_exotel_handshake(websocket)
    user = await get_user_by_phone(call_data["from"])

    # Build and run the voice pipeline
    await run_voice_pipeline(websocket, call_data, user)
```

**Audio format:** Exotel streams 8kHz, 16-bit, mono PCM, base64-encoded in JSON. Chunks must be multiples of 320 bytes.

---

## 6. Voice Pipeline - Streaming ASR/LLM/TTS

### 6A. Pipeline Construction (Pipecat)

```python
# /app/voice/pipeline.py

async def run_voice_pipeline(websocket, call_data, user):
    # 1. Exotel transport (handles WebSocket <-> audio frames)
    serializer = ExotelFrameSerializer(
        stream_id=call_data["stream_id"],
        call_id=call_data["call_id"],
        account_sid=call_data["account_sid"],
        api_key=EXOTEL_API_KEY,
        api_token=EXOTEL_API_TOKEN,
    )
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    # 2. ASR (Sarvam streaming)
    stt = SarvamSTTService(
        api_key=SARVAM_API_KEY,
        language="hi-IN",
        sample_rate=8000,
    )

    # 3. LLM (Bedrock Claude)
    llm = BedrockConverseLLMService(
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        region="ap-south-1",
        tools=get_tool_definitions(),
        system_prompt=get_system_prompt(user),
    )

    # 4. TTS (Sarvam streaming)
    tts = SarvamTTSService(
        api_key=SARVAM_API_KEY,
        speaker="meera",
        language="hi-IN",
        sample_rate=8000,
        audio_format="pcm_s16le",
    )

    # 5. Build and run pipeline
    pipeline = Pipeline([
        transport.input(),
        stt,
        llm,
        tts,
        transport.output(),
    ])

    task = PipelineTask(pipeline, params=PipelineParams(
        audio_in_sample_rate=8000,
        audio_out_sample_rate=8000,
    ))
    await task.run()
```

### 6B. Sarvam ASR Configuration

- **Model:** `saaras:v2.5` for auto-language detection (first utterance), then `saarika:v2.5` with detected language
- **Audio format:** `pcm_s16le`, base64-encoded
- **Sample rate:** 8000 Hz (matching Exotel)
- **VAD sensitivity:** `high_vad_sensitivity=True` (noisy rural environments)
- **Supported languages:** hi-IN, ta-IN, te-IN, mr-IN, kn-IN, bn-IN, gu-IN, ml-IN, pa-IN, or-IN, en-IN

### 6C. Sarvam TTS Configuration

- **Audio codec:** `pcm_s16le` (raw PCM to match Exotel)
- **Sample rate:** 8000 Hz
- **Pace:** 0.9 (slightly slower for rural clarity)
- **Streaming:** Send text chunks (max 500 chars), send `flush` after each sentence
- **Voices:** "meera" (Hindi female), language-specific voices for other languages

---

## 7. LLM Agent - Bedrock Claude

### 7A. System Prompt

```python
# /app/agent/prompts.py

SYSTEM_PROMPT = """
You are Gram Sathi, a friendly AI assistant for Indian farmers.
You speak to farmers over phone calls.

CRITICAL RULES:
1. Keep ALL responses under 3 short sentences. Farmers are
   listening on a phone -- long responses waste their time.
2. Respond in the SAME LANGUAGE the farmer speaks. Hindi -> Hindi.
   Tamil -> Tamil.
3. Use simple, everyday language. No technical jargon.
4. Always use tools to get real data. NEVER make up prices,
   weather, or scheme information.
5. If you need info (location, crop), ask ONE question at a time.
6. Prices: use "rupaye per quintal" format.
7. Weather: focus on rain, temperature, warnings.
8. Schemes: explain benefit amount and how to apply simply.
9. End each response with a brief follow-up suggestion.

FARMER PROFILE:
- Name: {user_name}
- Phone: {phone_number}
- State: {state}
- District: {district}
- Primary Crops: {crops}
- Land Size: {land_acres} acres
- Category: {farmer_category}

If profile fields are empty, naturally ask during conversation.

Current date: {current_date}
Current season: {current_season}
"""
```

### 7B. Tool Definitions

| Tool | Input | Source | Description |
|------|-------|--------|-------------|
| `get_mandi_prices` | commodity, state, district? | data.gov.in | Current commodity prices from nearby mandis (₹/quintal) |
| `get_weather_forecast` | district, state | IndianAPI.in | 5-day forecast: temp, rainfall, humidity, warnings |
| `check_scheme_eligibility` | category, state, crop, land_acres, caste, gender, age | Amazon Q | Match against 1000+ govt schemes from MyScheme.gov.in |
| `get_crop_advisory` | crop, state, query_type | Crop calendar + LLM | Sowing, irrigation, pest, fertilizer, harvest advice |
| `check_pm_kisan_status` | phone_number, aadhaar_last4? | Cached data | PM-KISAN payment status and next installment |

### 7C. Bedrock Converse API with Tool Use Loop

```python
# /app/agent/bedrock_agent.py

class BedrockAgent:
    def __init__(self, model_id, region, tools, system_prompt):
        self.client = boto3.client("bedrock-runtime", region_name=region)
        self.model_id = model_id
        self.tool_config = {"tools": tools}
        self.system_prompt = [{"text": system_prompt}]
        self.conversation_history = []

    async def process(self, user_text: str) -> str:
        self.conversation_history.append({
            "role": "user",
            "content": [{"text": user_text}]
        })

        while True:
            response = self.client.converse_stream(
                modelId=self.model_id,
                messages=self.conversation_history,
                system=self.system_prompt,
                toolConfig=self.tool_config,
            )

            assistant_msg, stop_reason = await self._process_stream(response)
            self.conversation_history.append(assistant_msg)

            if stop_reason == "tool_use":
                tool_results = await self._execute_tools(assistant_msg)
                self.conversation_history.append({
                    "role": "user",
                    "content": tool_results,
                })
                continue  # Loop for final text response

            elif stop_reason == "end_turn":
                return self._extract_text(assistant_msg)
```

---

## 8. Knowledge Base - Amazon Q

### 8A. Setup

1. Create Amazon Q Business application in ap-south-1
2. Create a custom data source connector
3. Ingest MyScheme HuggingFace dataset (`shrijayan/gov_myscheme`)
   - Contains: scheme name, description, eligibility criteria, benefits, application process
   - 1000+ central and state government schemes
   - Available in CSV, JSON, Parquet formats
4. Convert to structured documents, upload via BatchPutDocument API
5. Configure retrieval for eligibility-based queries

### 8B. Client

```python
# /app/knowledge/amazon_q_client.py

class AmazonQSchemeSearcher:
    def __init__(self, application_id):
        self.client = boto3.client("qbusiness", region_name="ap-south-1")
        self.application_id = application_id

    async def search_schemes(self, query: str) -> list:
        response = self.client.chat_sync(
            applicationId=self.application_id,
            userMessage=query,
        )
        return self._parse_results(response)
```

### 8C. Data Seeding

```python
# /scripts/seed_schemes.py

from datasets import load_dataset

def load_myscheme_data():
    dataset = load_dataset("shrijayan/gov_myscheme")
    schemes = []
    for row in dataset["train"]:
        schemes.append({
            "name": row["scheme_name"],
            "description": row["description"],
            "eligibility": row["eligibility_criteria"],
            "benefits": row["benefits"],
            "application_process": row["application_process"],
        })
    return schemes
```

---

## 9. Tool Implementations

### 9A. Mandi Prices

```python
# /app/tools/mandi_prices.py

class MandiPriceTool:
    API_URL = "https://api.data.gov.in/resource/{resource_id}"

    async def get_prices(self, commodity, state, district=None):
        # 1. Check Redis cache (TTL: 30 min)
        cached = await redis.get(f"mandi:{commodity}:{state}:{district}")
        if cached:
            return json.loads(cached)

        # 2. Query data.gov.in
        params = {
            "api-key": DATAGOV_API_KEY,
            "format": "json",
            "filters[commodity]": commodity.capitalize(),
            "filters[state]": state.capitalize(),
            "limit": 10,
        }
        if district:
            params["filters[district]"] = district

        response = await httpx.AsyncClient().get(self.API_URL, params=params)
        records = response.json().get("records", [])

        # 3. Format and cache
        result = {
            "commodity": commodity,
            "prices": [{
                "mandi": r["market"],
                "min_price": r["min_price"],
                "max_price": r["max_price"],
                "modal_price": r["modal_price"],
                "date": r["arrival_date"],
            } for r in records[:5]],
        }
        await redis.set(f"mandi:{commodity}:{state}:{district}",
                       json.dumps(result), ex=1800)
        return result
```

### 9B. Weather

```python
# /app/tools/weather.py
# Using IndianAPI.in (free 1000 requests, no IP whitelisting)

class WeatherTool:
    API_URL = "https://indianapi.in/api/weather"

    async def get_forecast(self, district, state):
        cached = await redis.get(f"weather:{district}:{state}")
        if cached:
            return json.loads(cached)

        response = await httpx.AsyncClient().get(
            self.API_URL,
            params={"city": district},
            headers={"X-Api-Key": INDIAN_API_KEY},
        )
        data = response.json()

        # Cache for 2 hours
        await redis.set(f"weather:{district}:{state}",
                       json.dumps(data), ex=7200)
        return data
```

### 9C. Scheme Eligibility

Calls Amazon Q Business with a natural language query constructed from farmer's profile.

### 9D. PM-KISAN

Since there's no public API, use cached/hardcoded data for demo. In production, this would use an official integration.

### 9E. Crop Advisory

Combines static crop calendar data (sowing/harvesting seasons by region) with weather tool output and Bedrock Claude's agricultural knowledge.

---

## 10. Database Schema

```sql
-- Users: progressively built from phone calls
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number VARCHAR(15) UNIQUE NOT NULL,
    name VARCHAR(100),
    state VARCHAR(50),
    district VARCHAR(100),
    village VARCHAR(100),
    primary_crops TEXT[],
    land_acres DECIMAL(6,2),
    farmer_category VARCHAR(20),  -- small/marginal/medium/large
    caste_category VARCHAR(10),   -- general/obc/sc/st
    gender VARCHAR(10),
    age INTEGER,
    preferred_language VARCHAR(10) DEFAULT 'hi-IN',
    total_calls INTEGER DEFAULT 0,
    last_call_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Call logs
CREATE TABLE call_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    exotel_call_sid VARCHAR(100),
    direction VARCHAR(10),       -- inbound/outbound/alert
    call_type VARCHAR(20),       -- missed_call/callback/proactive
    status VARCHAR(20),          -- initiated/answered/completed/failed
    duration_seconds INTEGER,
    language_detected VARCHAR(10),
    recording_url TEXT,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Conversation turns within a call
CREATE TABLE conversation_turns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_log_id UUID REFERENCES call_logs(id),
    turn_number INTEGER,
    role VARCHAR(10),            -- user/assistant
    transcript TEXT,
    tools_used TEXT[],
    tool_results JSONB,
    latency_ms INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Cached mandi prices (refreshed every 30 min)
CREATE TABLE mandi_prices (
    id SERIAL PRIMARY KEY,
    commodity VARCHAR(100),
    state VARCHAR(50),
    district VARCHAR(100),
    mandi_name VARCHAR(200),
    min_price DECIMAL(10,2),
    max_price DECIMAL(10,2),
    modal_price DECIMAL(10,2),
    arrival_date DATE,
    fetched_at TIMESTAMP DEFAULT NOW()
);

-- Proactive alerts queue
CREATE TABLE alert_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    alert_type VARCHAR(30),     -- weather_warning/price_spike/scheme_deadline
    message TEXT,
    priority INTEGER DEFAULT 5,
    status VARCHAR(20),         -- pending/calling/delivered/failed
    scheduled_at TIMESTAMP,
    delivered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_users_phone ON users(phone_number);
CREATE INDEX idx_call_logs_user ON call_logs(user_id);
CREATE INDEX idx_mandi_lookup ON mandi_prices(commodity, state, arrival_date);
CREATE INDEX idx_alerts_pending ON alert_queue(status, scheduled_at);
```

**Redis usage:**
- Session cache: active call sessions + conversation state (TTL: 1hr)
- Rate limiting: prevent duplicate callbacks to same number
- Price cache: mandi prices by commodity+state (TTL: 30 min)
- Weather cache: forecasts by district (TTL: 2 hrs)

---

## 11. Frontend Dashboard

### Streamlit Pages

1. **Live Call Monitor** - Active calls, real-time transcript updates
2. **Call History** - Table: duration, language, topics, recording playback
3. **User Profiles** - Farmers with progressive profile data
4. **Query Analytics** - Charts: most common queries, language distribution, tool usage
5. **Alert Queue** - Pending and delivered proactive alerts
6. **System Health** - API latency metrics, error rates, Exotel balance

### API Endpoints

```
GET  /api/dashboard/calls          # Paginated call logs
GET  /api/dashboard/users          # User list with stats
GET  /api/dashboard/analytics      # Aggregated query data
GET  /api/dashboard/alerts         # Alert queue status
WS   /api/dashboard/live           # Real-time call updates
GET  /api/health                   # Health check
```

---

## 12. Proactive Alerts System

### Scheduled Jobs (APScheduler)

| Job | Frequency | Action |
|-----|-----------|--------|
| Weather Monitor | Every 2 hours | Fetch weather for all districts with registered users. Alert if heavy rain >50mm, heatwave >45C, frost <4C |
| Price Monitor | Every 6 hours | Fetch mandi prices for users' crops. Alert if price spike >15% or drop >10% vs 7-day average |
| Alert Dispatcher | Every 15 minutes | Pick pending alerts, rate limit (max 1/user/day), trigger outbound calls via Exotel |

### Alert Call Flow

Simpler than the main flow -- TTS-only, no ASR needed initially:
1. System calls farmer via Exotel
2. Plays pre-generated TTS message with the alert
3. Optionally: "Press 1 to talk to Gram Sathi for more details" (DTMF -> full voice bot)

---

## 13. Build Sequence

### Phase 1: Core Voice Loop (MUST HAVE for demo)

| # | Task | Est. Time |
|---|------|-----------|
| 1 | Project scaffolding: FastAPI, Docker Compose (Postgres + Redis), config | 1 hr |
| 2 | Exotel setup: ExoPhone, API keys, App Bazaar flow with Voicebot | 1 hr |
| 3 | Sarvam AI setup: API key, test ASR/TTS endpoints | 0.5 hr |
| 4 | AWS Bedrock setup: enable Claude in ap-south-1, test Converse API | 0.5 hr |
| 5 | WebSocket endpoint `/ws/voice` for Exotel audio | 1 hr |
| 6 | Sarvam ASR service (streaming WebSocket) | 1.5 hr |
| 7 | Sarvam TTS service (streaming WebSocket) | 1.5 hr |
| 8 | Bedrock Agent: basic Converse with system prompt (no tools) | 1 hr |
| 9 | Pipeline integration: Exotel -> ASR -> LLM -> TTS -> Exotel | 2 hr |

**Milestone:** Call ExoPhone -> speak Hindi -> get AI voice response back

### Phase 2: Missed Call + Tools (DEMO READY)

| # | Task | Est. Time |
|---|------|-----------|
| 10 | Missed call webhook handler | 1 hr |
| 11 | Outbound callback trigger | 1.5 hr |
| 12 | Mandi price tool (data.gov.in) | 1.5 hr |
| 13 | Weather tool (IndianAPI.in) | 1 hr |
| 14 | Register tools in Bedrock toolConfig | 1 hr |
| 15 | Database: user profiles + call logs | 1 hr |
| 16 | Progressive profile building | 1 hr |

**Milestone:** Missed call -> callback -> voice with live mandi prices + weather

### Phase 3: Knowledge Base + Dashboard (IMPRESSIVE DEMO)

| # | Task | Est. Time |
|---|------|-----------|
| 17 | Amazon Q setup: create app, ingest MyScheme data | 2 hr |
| 18 | Scheme eligibility tool (Amazon Q) | 1.5 hr |
| 19 | Crop advisory tool | 1 hr |
| 20 | Streamlit dashboard | 2 hr |
| 21 | Latency optimization | 1.5 hr |

**Milestone:** Full features with scheme matching, crop advice, dashboard

### Phase 4: Alerts + Polish (STRETCH GOALS)

| # | Task | Est. Time |
|---|------|-----------|
| 22 | Proactive alert scheduler | 2 hr |
| 23 | Alert outbound calls | 1 hr |
| 24 | Multi-language tuning (Hindi + Tamil/Telugu) | 1 hr |
| 25 | Demo rehearsal: seed data, script, test 10+ times | 1 hr |

---

## 14. Demo Strategy

### The 3-Minute Demo Script

| Time | What | Script |
|------|------|--------|
| 0:00-0:30 | **The Hook** | "300 million Indians cannot use any AI app you've ever built. No smartphone. No internet. No app store. But they all have one thing -- a phone number." [Hold up a feature phone] |
| 0:30-1:00 | **The Missed Call** | "Watch." [Dial number on speaker, let ring 3 times, hang up] "That missed call just told our AI: this farmer needs help." [Wait 5 seconds, phone rings] "Gram Sathi is calling back. Free of cost." |
| 1:00-2:15 | **Live Voice Interaction** | Answer on speaker. AI greets in Hindi. Ask: (1) "Lucknow mein aaj gehu ka kya bhav hai?" -> real mandi price (2) "Kal barish hogi kya?" -> weather forecast (3) "Mujhe koi sarkari yojana mil sakti hai?" -> scheme match |
| 2:15-2:45 | **Dashboard** | Switch to laptop. Show: live call log, farmer profile being built, query analytics |
| 2:45-3:00 | **Impact** | "Every farmer in India. One missed call away from AI. No smartphone. No internet. No app. If we reach 1% of UP's feature phone users -- that's 2 million farmers." |

### Demo Preparation Checklist

- [ ] Pre-test the number 10+ times
- [ ] Have a backup recording of a perfect interaction
- [ ] Pre-seed user profile for demo phone number (state, district pre-filled)
- [ ] Pre-cache mandi prices and weather for demo location
- [ ] Set TTS pace to 0.9 for clarity
- [ ] Test in a quiet room or use Bluetooth speaker
- [ ] Have dashboard open on second screen/tab
- [ ] Test Hindi + one South Indian language (Tamil/Telugu)
- [ ] Have a second phone ready as backup
- [ ] Time the full demo to stay under 3 minutes

---

## 15. Environment Variables

```env
# Exotel
EXOTEL_ACCOUNT_SID=your_account_sid
EXOTEL_API_KEY=your_api_key
EXOTEL_API_TOKEN=your_api_token
EXOTEL_EXOPHONE=your_exophone_number
EXOTEL_VOICEBOT_APP_ID=your_app_id

# Sarvam AI
SARVAM_API_KEY=your_sarvam_key

# AWS
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_DEFAULT_REGION=ap-south-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
AMAZON_Q_APPLICATION_ID=your_q_app_id

# Bhashini (fallback)
BHASHINI_USER_ID=your_user_id
BHASHINI_API_KEY=your_bhashini_key

# Data APIs
DATAGOV_API_KEY=your_datagov_key
INDIAN_API_KEY=your_indianapi_key

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/gramsathi
REDIS_URL=redis://localhost:6379/0

# Server
SERVER_URL=https://your-server.com  # Public URL (use ngrok for dev)
PORT=8000
```

---

## 16. Dependencies

```
# requirements.txt

# Core
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
python-dotenv>=1.0.0
pydantic-settings>=2.0.0
httpx>=0.27.0

# Telephony / Voice Pipeline
pipecat-ai>=0.0.54
websockets>=13.0

# AWS
boto3>=1.35.0

# Database
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.30.0
alembic>=1.14.0
redis>=5.0.0

# Scheduling
apscheduler>=3.10.0

# Data
datasets>=3.0.0            # HuggingFace datasets for MyScheme

# Dashboard
streamlit>=1.40.0

# Utilities
python-multipart>=0.0.9    # Form data parsing
```

---

## 17. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Exotel WebSocket instability | Call drops | Reconnection logic; pre-recorded fallback audio |
| Sarvam ASR accuracy with rural accents | Wrong transcription | High VAD sensitivity; confirmation prompts ("Aapne kaha: gehu ka bhav. Kya sahi hai?") |
| Voice pipeline latency >2s | Poor UX | Sentence-level TTS streaming; filler phrases; connection pooling |
| Bedrock tool loop takes multiple rounds | 3-5s delays | Max 2 tool recursion; pre-fill user profile |
| data.gov.in API unreliable | No mandi prices | Aggressive caching (Postgres + Redis); background refresh every 30 min |
| Demo failure on stage | Embarrassment | Backup recording; seed all data; rehearse 10x; second phone ready |
| Exotel trial credit limits | Run out | Track usage; keep test calls short; ~₹2/min = ~500 min available |
| ngrok tunnel instability (dev) | WebSocket drops | Use a stable tunnel or deploy to EC2 for demo |

---

## 18. API Reference Links

### Telephony
- Exotel Developer Portal: https://developer.exotel.com/api
- Exotel Voice Streaming: https://exotel.com/products/voice-streaming/
- Exotel Pricing: https://exotel.com/pricing/

### Speech AI
- Sarvam AI Docs: https://docs.sarvam.ai
- Sarvam STT Streaming: https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/speech-to-text/streaming-api
- Sarvam TTS: https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/text-to-speech
- Bhashini APIs: https://bhashini.gitbook.io/bhashini-apis
- Bhashini WebSocket ASR: https://dibd-bhashini.gitbook.io/bhashini-apis/websocket-asr-api
- Bhashini Registration: https://bhashini.gov.in/ulca/user/register

### AWS
- Bedrock Converse API: https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference-call.html
- Bedrock Models by Region: https://docs.aws.amazon.com/bedrock/latest/userguide/models-regions.html
- Amazon Q Business: https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/what-is.html
- Bedrock Pricing: https://aws.amazon.com/bedrock/pricing/

### Government Data
- data.gov.in: https://www.data.gov.in/
- eNAM: https://enam.gov.in
- PM-KISAN: https://pmkisan.gov.in
- MyScheme: https://www.myscheme.gov.in/
- MyScheme HuggingFace Dataset: https://huggingface.co/datasets/shrijayan/gov_myscheme
- IndianAPI Weather: https://indianapi.in/weather-api
- IMD Weather API Docs: https://mausam.imd.gov.in/imd_latest/contents/api.pdf

### Voice AI Architecture
- Pipecat Framework: https://github.com/pipecat-ai/pipecat
- Real-Time Voice Agent Latency: https://cresta.com/blog/engineering-for-real-time-voice-agent-latency
- Low-Latency Voice Agents Paper: https://arxiv.org/html/2508.04721v1
