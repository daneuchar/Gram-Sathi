# Gram Sathi - Architecture Sequence Diagrams

## 1. Main Call Flow (End-to-End)

```mermaid
sequenceDiagram
    box rgb(255, 87, 51) FARMER
        participant F as 📱 Farmer<br/>(Feature Phone)
    end
    box rgb(138, 43, 226) TELEPHONY
        participant EX as ☎️ Exotel<br/>(Cloud Telephony)
    end
    box rgb(0, 191, 255) BACKEND
        participant API as ⚡ FastAPI<br/>(App Server)
        participant WS as 🔌 WebSocket<br/>(Voice Channel)
    end
    box rgb(255, 165, 0) VOICE PIPELINE (Pipecat)
        participant ASR as 🎤 Sarvam ASR<br/>(Speech→Text)
        participant LLM as 🧠 Bedrock Claude<br/>(AI Agent)
        participant TTS as 🔊 Sarvam TTS<br/>(Text→Speech)
    end
    box rgb(0, 200, 83) DATA SERVICES
        participant TOOLS as 🔧 Tool Executor
        participant DB as 🗄️ PostgreSQL
        participant RD as ⚡ Redis Cache
    end

    Note over F,RD: 🌾 PHASE 1: MISSED CALL TRIGGER (₹0 for Farmer)

    F->>+EX: ① Missed Call (Dial & Hang Up)
    activate F
    EX->>+API: POST /webhooks/exotel/missed-call<br/>{CallSid, From, Status}
    API->>DB: INSERT call_logs (direction: inbound)
    API->>DB: UPSERT user profile (phone_number)
    API-->>-EX: 200 OK

    Note over API: ⏱️ 5-second delay<br/>(avoid calling during hangup)

    API->>+EX: POST /exotel/callback<br/>(Initiate Outbound Call)
    EX->>F: ② Callback Ring 📞
    F-->>EX: Farmer Answers ✅
    EX-->>-API: Call Connected (status webhook)
    API->>DB: UPDATE call_logs (status: connected)

    Note over F,RD: 🎙️ PHASE 2: VOICE PIPELINE ACTIVATION

    EX->>+WS: WebSocket Connect /ws/voice<br/>(8kHz PCM Audio Stream)
    WS->>DB: LOAD user profile & history
    WS->>RD: LOAD session state

    Note over F,RD: 🗣️ PHASE 3: CONVERSATION LOOP (Repeats per Turn)

    rect rgb(40, 40, 80)
        Note right of F: 🔄 Conversation Turn

        F->>EX: ③ Farmer Speaks (Voice)
        EX->>WS: Audio Frames (base64 PCM JSON)
        WS->>+ASR: Stream Audio Chunks
        ASR-->>-WS: Transcript (auto language detect)

        WS->>DB: INSERT conversation_turns<br/>(turn, transcript, language)

        WS->>+LLM: Send Transcript + Context<br/>(Converse Stream API)

        alt 🔧 Tool Call Required
            LLM->>+TOOLS: Function Call<br/>(tool_name, args)

            par Parallel Tool Execution
                TOOLS->>RD: Check Cache
                RD-->>TOOLS: Cache Miss ❌
                TOOLS->>TOOLS: Call External API<br/>(data.gov.in / IndianAPI / Amazon Q)
                TOOLS->>RD: SET cache (TTL: 30m/2h)
            end

            TOOLS-->>-LLM: Tool Results (JSON)
        end

        LLM-->>-WS: Response Tokens (streaming)

        WS->>+TTS: Stream Text → Speech
        TTS-->>-WS: Audio Chunks (PCM)

        WS->>EX: Audio Response Frames
        EX->>F: ④ Farmer Hears Response 🔊

        WS->>DB: UPDATE conversation_turns<br/>(response, tools_used, latency_ms)
    end

    Note over F,RD: 📴 PHASE 4: CALL END

    F->>EX: ⑤ Farmer Hangs Up
    EX->>WS: Disconnect Event
    deactivate WS
    WS->>DB: UPDATE call_logs<br/>(duration, ended_at, recording_url)
    WS->>RD: CLEANUP session state
    deactivate F
```

## 2. Tool Execution Detail Flow

```mermaid
sequenceDiagram
    box rgb(0, 191, 255) AI ENGINE
        participant LLM as 🧠 Bedrock Claude
    end
    box rgb(255, 87, 51) TOOL ROUTER
        participant TR as 🔧 Tool Executor
    end
    box rgb(138, 43, 226) EXTERNAL APIs
        participant MP as 📊 data.gov.in<br/>(Mandi Prices)
        participant WX as 🌦️ IndianAPI.in<br/>(Weather)
        participant AQ as 📚 Amazon Q<br/>(Scheme KB)
        participant CA as 🌾 Crop Advisory<br/>(Static + LLM)
    end
    box rgb(0, 200, 83) CACHE
        participant RD as ⚡ Redis
    end

    LLM->>TR: function_call: get_mandi_prices<br/>{commodity: "wheat", state: "UP"}

    TR->>RD: GET mandi:wheat:UP:lucknow

    alt Cache HIT ✅
        RD-->>TR: Cached Price Data
    else Cache MISS ❌
        RD-->>TR: null
        TR->>+MP: GET /resource?commodity=wheat&state=UP<br/>Header: api-key={DATAGOV_KEY}
        MP-->>-TR: {price: ₹2,450/quintal, market: "Lucknow"}
        TR->>RD: SET mandi:wheat:UP:lucknow (TTL: 30min)
    end

    TR-->>LLM: ToolResult: {prices: [...]}

    LLM->>TR: function_call: get_weather<br/>{district: "Lucknow", state: "UP"}

    TR->>RD: GET weather:lucknow:UP

    alt Cache HIT ✅
        RD-->>TR: Cached Weather Data
    else Cache MISS ❌
        RD-->>TR: null
        TR->>+WX: GET /weather?district=Lucknow<br/>Header: X-Api-Key={INDIAN_KEY}
        WX-->>-TR: {temp: 32°C, rain: 15mm, humidity: 65%}
        TR->>RD: SET weather:lucknow:UP (TTL: 2hr)
    end

    TR-->>LLM: ToolResult: {forecast: [...]}

    LLM->>TR: function_call: check_scheme_eligibility<br/>{farmer_profile: {...}}

    TR->>+AQ: Amazon Q Chat API<br/>query: "schemes for small farmer UP wheat"
    AQ-->>-TR: {schemes: ["PM-KISAN", "PMFBY", ...]}

    TR-->>LLM: ToolResult: {eligible_schemes: [...]}

    Note over LLM: Synthesize all tool results<br/>into farmer-friendly response<br/>in detected language
```

## 3. Proactive Alert System Flow

```mermaid
sequenceDiagram
    box rgb(255, 165, 0) SCHEDULER
        participant SC as ⏰ APScheduler
    end
    box rgb(138, 43, 226) MONITORS
        participant WM as 🌦️ Weather Monitor<br/>(Every 2 Hours)
        participant PM as 📊 Price Monitor<br/>(Every 6 Hours)
    end
    box rgb(0, 191, 255) DISPATCH
        participant AD as 📢 Alert Dispatcher<br/>(Every 15 Minutes)
    end
    box rgb(0, 200, 83) STORAGE
        participant DB as 🗄️ PostgreSQL
        participant RD as ⚡ Redis
    end
    box rgb(255, 87, 51) DELIVERY
        participant EX as ☎️ Exotel
        participant F as 📱 Farmer
    end

    Note over SC,F: 🔍 PHASE 1: MONITORING & DETECTION

    SC->>+WM: Trigger Weather Check
    WM->>RD: Fetch cached weather for all districts

    alt 🚨 Severe Weather Detected
        Note over WM: Heavy Rain >50mm<br/>Heatwave >45°C<br/>Frost <4°C
        WM->>DB: INSERT alert_queue<br/>{type: weather_warning,<br/>priority: 9, status: pending}
    end
    deactivate WM

    SC->>+PM: Trigger Price Check
    PM->>RD: Fetch cached mandi prices
    PM->>DB: Compare with historical prices

    alt 📈 Price Spike/Drop Detected
        Note over PM: Spike >15%<br/>Drop >10%
        PM->>DB: INSERT alert_queue<br/>{type: price_spike,<br/>priority: 7, status: pending}
    end
    deactivate PM

    Note over SC,F: 📤 PHASE 2: ALERT DISPATCH (Rate Limited)

    SC->>+AD: Trigger Dispatch Cycle
    AD->>DB: SELECT * FROM alert_queue<br/>WHERE status='pending'<br/>AND scheduled_at <= NOW()
    DB-->>AD: Pending Alerts [{user, message, priority}]

    loop For Each Alert (max 1/user/day)
        AD->>DB: Check rate limit (last alert time)

        alt ✅ Within Rate Limit
            AD->>DB: UPDATE alert status → 'calling'
            AD->>+EX: POST /exotel/outbound-call<br/>{to: farmer_phone, message: alert_text}
            EX->>F: 📞 Outbound Alert Call
            F-->>EX: Farmer Answers
            EX->>F: 🔊 TTS Alert Message

            Note over F: "Heavy rain expected tomorrow.<br/>Press 1 to talk to Gram Sathi"

            alt Farmer Presses 1 (DTMF)
                F->>EX: DTMF: 1
                EX->>AD: Transfer to Voice Bot
                Note over AD,F: → Full Conversation Flow Begins
            else Farmer Listens & Hangs Up
                F->>EX: Hang Up
            end

            EX-->>-AD: Call Status: completed
            AD->>DB: UPDATE alert status → 'delivered'
        else ❌ Rate Limit Exceeded
            AD->>DB: UPDATE scheduled_at → tomorrow
        end
    end
    deactivate AD
```

## 4. Dashboard & Monitoring Flow

```mermaid
sequenceDiagram
    box rgb(255, 87, 51) DASHBOARD
        participant ST as 📊 Streamlit<br/>(Analytics UI)
    end
    box rgb(0, 191, 255) BACKEND
        participant API as ⚡ FastAPI
    end
    box rgb(0, 200, 83) DATA
        participant DB as 🗄️ PostgreSQL
        participant RD as ⚡ Redis
    end
    box rgb(138, 43, 226) LIVE
        participant WS as 🔌 WebSocket<br/>/api/dashboard/live
    end

    Note over ST,WS: 📈 REAL-TIME MONITORING

    ST->>+API: GET /api/dashboard/calls<br/>(Call History)
    API->>DB: SELECT * FROM call_logs<br/>JOIN users ON user_id<br/>ORDER BY started_at DESC
    DB-->>API: Call Records
    API-->>-ST: {calls: [...], total: 1234}

    ST->>+API: GET /api/dashboard/analytics<br/>(Aggregated Stats)
    API->>DB: Aggregate queries:<br/>topic distribution, language usage,<br/>tool utilization, avg duration
    DB-->>API: Analytics Data
    API-->>-ST: {charts: {topics, languages, tools}}

    ST->>+API: GET /api/dashboard/users<br/>(Farmer Profiles)
    API->>DB: SELECT * FROM users<br/>WITH call_count, last_call
    DB-->>API: User Profiles
    API-->>-ST: {users: [...], active: 456}

    ST->>+API: GET /api/health<br/>(System Health)
    API->>RD: PING
    RD-->>API: PONG ✅
    API->>DB: SELECT 1
    DB-->>API: OK ✅
    API-->>-ST: {db: healthy, cache: healthy,<br/>exotel_balance: ₹850, api_latency: 120ms}

    ST->>+WS: WebSocket Connect<br/>/api/dashboard/live

    loop Real-time Updates
        WS-->>ST: 🟢 New Call Started<br/>{user: "Ramesh", language: "Hindi"}
        WS-->>ST: 💬 Live Transcript<br/>"Wheat ka bhav kya hai?"
        WS-->>ST: 🔧 Tool Called: get_mandi_prices
        WS-->>ST: 🔴 Call Ended (duration: 2m 34s)
    end
    deactivate WS
```

## 5. Authentication & Service Integration

```mermaid
sequenceDiagram
    box rgb(0, 191, 255) BACKEND
        participant API as ⚡ FastAPI
    end
    box rgb(255, 165, 0) AUTH LAYER
        participant AUTH as 🔐 Credentials<br/>(.env / AWS IAM)
    end
    box rgb(138, 43, 226) SERVICES
        participant EX as ☎️ Exotel
        participant SAR as 🎤 Sarvam AI
        participant BED as 🧠 AWS Bedrock
        participant AQ as 📚 Amazon Q
        participant DG as 📊 data.gov.in
        participant IA as 🌦️ IndianAPI
    end

    Note over API,IA: 🔐 SERVICE AUTHENTICATION (No User Auth - Phone ID Only)

    API->>AUTH: Load credentials from .env

    API->>EX: Basic Auth (API_KEY:API_TOKEN)<br/>POST /Accounts/{sid}/Calls
    EX-->>API: ✅ Call Initiated

    API->>SAR: Bearer Token<br/>Authorization: Bearer {SARVAM_API_KEY}<br/>WebSocket: wss://api.sarvam.ai
    SAR-->>API: ✅ ASR/TTS Stream Ready

    API->>AUTH: AWS IAM Role / Access Keys
    AUTH-->>API: Signed Request Headers

    API->>BED: SigV4 Signed Request<br/>POST bedrock-runtime.ap-south-1<br/>/model/anthropic.claude-3-5-sonnet/converse-stream
    BED-->>API: ✅ LLM Stream Ready

    API->>AQ: IAM Auth<br/>POST qbusiness.ap-south-1<br/>ChatSync {applicationId}
    AQ-->>API: ✅ Knowledge Base Response

    API->>DG: Query Param Auth<br/>GET /resource?api-key={DATAGOV_KEY}
    DG-->>API: ✅ Mandi Price Data

    API->>IA: Header Auth<br/>X-Api-Key: {INDIAN_API_KEY}
    IA-->>API: ✅ Weather Forecast Data
```
