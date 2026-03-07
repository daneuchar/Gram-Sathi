# Gram Saathi — Requirements

## Problem

150M+ Indian farmers have no smartphone or internet — completely excluded from AI and digital agriculture. Every existing agri-tech solution requires an app or data connection, leaving the most vulnerable farmers behind.

## Solution

Gram Saathi: one missed call (₹0) triggers an AI voice callback delivering live market prices, weather forecasts, government scheme eligibility, and crop advice — in the farmer's own language, on any phone.

## Functional Requirements

### FR1: Missed Call & Callback
- System detects missed calls on a virtual phone number
- Automatically calls the farmer back within 5 seconds
- Farmer pays ₹0 — entire cost borne by the system

### FR2: Voice Conversation in Regional Languages
- Real-time speech-to-text and text-to-speech in 22+ Indian languages
- Auto-detect the farmer's language from first utterance
- Respond in the same language the farmer speaks
- End-to-end voice — no text, no menus, no screens

### FR3: Live Mandi Prices
- Fetch real-time commodity prices from data.gov.in (1,266 mandis across India)
- Return prices in ₹/quintal for the farmer's nearest markets
- Cache with 30-minute refresh -> caching in memory ( at start of application )

### FR4: Weather Forecast
- Provide 5-day hyperlocal weather forecast (temperature, rainfall, humidity)
- Alert for severe conditions: heavy rain >50mm, heatwave >45°C, frost <4°C ( cached for 2 locations and rotate cache  ) 

### FR5: Government Scheme Matching
- Match farmer profile against 1,000+ central and state government schemes
- Source: MyScheme.gov.in dataset via Amazon Q Business
- Return eligibility, benefit amount, and how to apply

### FR6: Crop Advisory ( mordern farming techniques )
- Season-aware, region-specific farming guidance
- Sowing, irrigation, pest management, fertilizer, and harvest advice

### FR7: Progressive Farmer Profile ( IMPORTANT )
- Build farmer profile naturally through conversation (state, district, crops, land size)
- Personalize all responses based on accumulated profile data
- No registration or form-filling required

### FR8: Analytics Dashboard
- Real-time call monitoring with live transcripts
- Call history, user profiles, query analytics
- System health and API latency metrics

## Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Voice latency (end-of-speech → first audio response) | < 1.5 seconds |
| Supported languages | 22+ Indian languages |
| Device compatibility | Any phone (feature phone, smartphone, landline) |
| Cost to farmer | ₹0 (missed call model) |
| Availability | 99.5% uptime |
| Concurrent calls | 10+ simultaneous sessions |
| Data freshness — prices | ≤ 30 minutes |
| Data freshness — weather | ≤ 2 hours |

## Constraints

- Must use **Amazon Bedrock** as the LLM provider
- Must use **Amazon Q Business** as the knowledge base
- Must use **Kiro** as the development IDE
- No smartphone or internet required on the farmer's end
- Must work on basic feature phones via voice only

## User Personas

### Primary: Small/Marginal Farmer
- Owns < 5 acres, earns ₹5,000–8,000/month
- Has a basic feature phone, no internet
- Speaks Hindi, Tamil, Telugu, or other regional language
- Needs: daily mandi prices, weather updates, scheme information

### Secondary: Dashboard Operator (NGO/Govt)
- Monitors call analytics and farmer engagement
- Tracks query patterns and system health
- Uses the Streamlit web dashboard

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Python |
| Voice Pipeline | Pipecat (open-source streaming framework) |
| Telephony | Cloud telephony provider (missed call + callback + WebSocket audio) |
| ASR | Sarvam AI — Saaras v3 (streaming, 22 languages) |
| TTS | Sarvam AI — Bulbul v3 (streaming, natural voices) |
| LLM | Amazon Bedrock — Claude (ap-south-1, Converse Stream API) |
| Knowledge Base | Amazon Q Business (MyScheme.gov.in dataset) |
| Database | PostgreSQL (persistent) + Redis (cache & sessions) |
| Dashboard | Streamlit |
| External APIs | data.gov.in (mandi prices), IndianAPI.in (weather) |
