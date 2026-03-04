# LiveKit Agents + Llama 3.3 70B Migration Design

**Date:** 2026-03-04
**Status:** Approved

## Overview

Migrate Gram Saathi from FastRTC + AWS Nova Lite to LiveKit Agents + Llama 3.3 70B (Bedrock). Replace the custom `process_turn_streaming()` pipeline with LiveKit's `VoicePipelineAgent`, backed by three custom plugins for Sarvam STT, Sarvam TTS, and Bedrock LLM.

## Architecture

### Current
```
Phone → Twilio Media Stream WebSocket → FastRTC → GramSaathiHandler
         └── process_turn_streaming(): Sarvam ASR → Nova Lite → Sarvam TTS
```

### New
```
Phone → Twilio SIP Trunk → LiveKit SIP → LiveKit Server
                                              │
                                    LiveKit Agent Worker (separate process)
                                    ├── SarvamSTT plugin (saaras:v3)
                                    ├── BedrockLLM plugin (Llama 3.3 70B)
                                    ├── SarvamTTS plugin (bulbul:v3)
                                    ├── Semantic Turn Detection (MultilingualModel)
                                    └── VoicePipelineAgent

FastAPI app (dashboard, webhooks) — retained, FastRTC removed
```

Two processes run side by side:
- `uvicorn app.main:app` — dashboard, webhook routes (unchanged)
- `python -m app.livekit_agent start` — LiveKit worker, polls for call jobs

## Custom Plugins

### SarvamSTT (`src/app/plugins/sarvam_stt.py`)
- Implements `livekit.agents.stt.STT`
- Buffers LiveKit 16kHz PCM audio frames until end-of-turn signal
- Encodes buffered frames as WAV, submits to Sarvam `saaras:v3`
- Mode: `translate` for Indic languages (English transcript), `transcribe` for English
- Language sourced from session userdata (farmer's stored preference)

### BedrockLLM (`src/app/plugins/bedrock_llm.py`)
- Implements `livekit.agents.llm.LLM`
- Model: `us.meta.llama3-3-70b-instruct-v1:0` (cross-region inference)
- Uses Bedrock Converse API — same `toolConfig` dict format as Nova Lite
- Tool calling: weather, mandi prices, schemes (unchanged tools registry)
- System prompt injected per-turn with farmer profile context
- Temperature: 0.3, max tokens: 256

### SarvamTTS (`src/app/plugins/sarvam_tts.py`)
- Implements `livekit.agents.tts.TTS`
- Wraps `bulbul:v3` streaming WebSocket
- Pre-processes text: strip markdown → expand numbers → translate English→farmer's language
- Language sourced from session userdata
- Streams audio chunks back to LiveKit as they arrive

## Agent Entrypoint & Session Management

**Entrypoint** (`src/app/livekit_agent.py`):
```python
async def entrypoint(ctx: JobContext):
    await ctx.connect()
    session = AgentSession(
        stt=SarvamSTT(),
        llm=BedrockLLM(),
        tts=SarvamTTS(),
        turn_detection=MultilingualModel(),
        before_llm_cb=inject_filler_audio,
    )
    agent = VoicePipelineAgent(session)
    agent.start(ctx.room)
```

**Session state** (replaces GramSaathiHandler instance variables):
- `ctx.room.metadata` / session `userdata` holds: farmer profile, language code, onboarding state
- Onboarding: same prompt-driven state machine — first turns collect name/location/language, write profile to DB, switch to main SYSTEM_PROMPT
- `PROFILE` marker extraction: `on_agent_message` hook parses marker, updates session userdata + DB

**Filler audio:**
- Injected via `before_llm_cb` on `VoicePipelineAgent`
- `classify_filler(transcript)` → push pre-recorded audio frames while LLM warms up
- Preserves the 0ms filler latency optimization

## Telephony Migration

**Step 1:** Create LiveKit SIP Trunk (LiveKit Cloud or self-hosted)
**Step 2:** Configure Twilio to route the phone number to the LiveKit SIP URI
**Step 3:** Remove FastRTC from `main.py`; add LiveKit dispatch webhook endpoint

**Inbound call flow:**
```
Twilio PSTN → LiveKit SIP → LiveKit Room → Agent worker picks up job → entrypoint() runs
```

## Llama 3.3 70B Optimizations

| Parameter | Nova Lite | Llama 3.3 70B |
|-----------|-----------|---------------|
| Model ID | `us.amazon.nova-lite-v1:0` | `us.meta.llama3-3-70b-instruct-v1:0` |
| Max tokens | 512 | 256 |
| Temperature | 0.3 | 0.3 |
| Tool calling | Bedrock Converse | Bedrock Converse (same format) |
| Thinking tags | Strip `<thinking>` | Not needed |

System prompt: remove `<thinking>` stripping note, simplify to pure instruction format. Llama 3.3 follows the "1-2 sentence voice response" instruction reliably.

## Files Changed

### New
- `src/app/livekit_agent.py` — agent entrypoint + worker
- `src/app/plugins/__init__.py`
- `src/app/plugins/sarvam_stt.py` — custom STT plugin
- `src/app/plugins/bedrock_llm.py` — custom LLM plugin
- `src/app/plugins/sarvam_tts.py` — custom TTS plugin

### Modified
- `src/app/main.py` — remove FastRTC, add LiveKit dispatch webhook
- `src/app/config.py` — add LiveKit URL, API key, Llama model ID

### Retired
- `src/app/handlers/gram_saathi.py`
- `src/app/pipeline/pipeline.py`
- `src/app/pipeline/nova_client.py`
- `src/app/pipeline/openai_client.py`

### Kept Unchanged
- `src/app/pipeline/sarvam_asr.py`
- `src/app/pipeline/sarvam_tts.py`
- `src/app/pipeline/sarvam_translate.py`
- `src/app/tools/` (entire directory)
- `src/app/database.py`
- `src/dashboard/`

## Dependencies Added

```
livekit-agents[silero,turn-detector]~=1.4
```

Sarvam STT/TTS and Bedrock LLM are custom plugins — no additional LiveKit plugin packages needed for them.
