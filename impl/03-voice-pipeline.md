# Task 03: Voice Pipeline

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Build the real-time voice pipeline: Exotel WebSocket audio → Sarvam ASR → Amazon Nova (Bedrock) → Sarvam TTS → audio back to farmer.

**Branch:** `feat/voice-pipeline`
**Worktree:** `../gramvaani-voice`
**Depends On:** Task 01 (backend-foundation merged)

**Architecture:** Pipecat orchestrates 3 concurrent streaming stages. Audio arrives as 8kHz PCM base64 JSON over WebSocket. Sarvam ASR transcribes → Nova generates response (with tool calls handled by Task 04 tools) → Sarvam TTS streams audio back sentence by sentence.

**Nova Model:** `amazon.nova-lite-v1:0` via Bedrock **Converse Stream** API (ap-south-1)

**Latency Strategy:**
1. **Filler phrase** — play "Haan ji, ek second..." via TTS the instant ASR finishes (~0ms wait)
2. **Streaming Nova** — `converse_stream()` not `converse()` — tokens arrive at ~200ms not ~900ms
3. **Sentence-level TTS** — split stream on `./?/!` → synthesize + send each sentence immediately, don't wait for full response
4. **Nova Lite over Pro** — 3x faster, adequate for simple Q&A + tool calls; upgrade to Pro only if quality issues found

---

## Setup

```bash
git checkout feat/backend-foundation
git pull
git checkout -b feat/voice-pipeline
```

---

### Step 1: Write failing test for Nova connection

**Create `tests/test_nova.py`:**

```python
import pytest
from unittest.mock import patch, MagicMock

@pytest.mark.asyncio
async def test_nova_client_initializes():
    from app.pipeline.nova_client import NovaClient
    client = NovaClient()
    assert client.model_id == "amazon.nova-lite-v1:0"
    assert client.region == "ap-south-1"

@pytest.mark.asyncio
async def test_nova_generates_response():
    from app.pipeline.nova_client import NovaClient
    client = NovaClient()
    with patch.object(client, "_call_bedrock", return_value="Jaipur mandi mein gehun ₹2,340 hai"):
        response = await client.generate("Jaipur ka gehun bhav batao", farmer_profile={})
    assert "₹" in response or len(response) > 0
```

**Run:** `pytest tests/test_nova.py -v`
Expected: FAIL — module not found.

---

### Step 2: Nova client

**Create `app/pipeline/__init__.py` and `app/pipeline/nova_client.py`:**

```python
import boto3
import json
import re
from typing import AsyncGenerator
from app.config import settings

SYSTEM_PROMPT = """You are Gram Saathi, an AI assistant for Indian farmers.
Rules:
- Respond in the SAME language the farmer speaks (Hindi, Tamil, Telugu, etc.)
- Keep responses under 3 short sentences — this is a phone call
- ALWAYS use tools for mandi prices, weather, and government schemes — never fabricate data
- Ask one question at a time if you need more information
- Be warm, respectful, and use simple language a rural farmer understands
- Address the farmer as 'aap' (Hindi) or equivalent honorific in their language
"""

# Sentence boundary pattern for streaming TTS split
SENTENCE_END = re.compile(r'(?<=[।.!?])\s+')

class NovaClient:
    def __init__(self):
        self.model_id = settings.bedrock_model_id  # amazon.nova-lite-v1:0
        self.region = settings.aws_default_region
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=self.region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )

    async def generate_stream(
        self, messages: list, tools: list = None
    ) -> AsyncGenerator[str | dict, None]:
        """
        Stream tokens from Nova via converse_stream().
        Yields:
          - str chunks as tokens arrive
          - dict {"toolUse": ...} when Nova calls a tool
        """
        kwargs = {
            "modelId": self.model_id,
            "system": [{"text": SYSTEM_PROMPT}],
            "messages": messages,
            "inferenceConfig": {"maxTokens": 256, "temperature": 0.7},
        }
        if tools:
            kwargs["toolConfig"] = {"tools": tools}

        response = self._client.converse_stream(**kwargs)
        tool_use_block = None
        tool_input_json = ""

        for event in response["stream"]:
            # Text token
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "text" in delta:
                    yield delta["text"]
                elif "toolUse" in delta:
                    tool_input_json += delta["toolUse"].get("input", "")

            # Tool use start
            elif "contentBlockStart" in event:
                start = event["contentBlockStart"].get("start", {})
                if "toolUse" in start:
                    tool_use_block = start["toolUse"]

            # Tool use complete
            elif "contentBlockStop" in event:
                if tool_use_block and tool_input_json:
                    tool_use_block["input"] = json.loads(tool_input_json)
                    yield {"toolUse": tool_use_block}
                    tool_use_block = None
                    tool_input_json = ""

    async def generate(self, user_text: str, farmer_profile: dict,
                       conversation_history: list = None, tools: list = None) -> str:
        """Non-streaming fallback — used for tool result follow-up turns."""
        messages = list(conversation_history or [])
        if user_text:
            content = user_text
            if len(messages) == 0 and farmer_profile:
                content += f"\n\n[Farmer Profile: {json.dumps(farmer_profile)}]"
            messages.append({"role": "user", "content": [{"text": content}]})

        full_text = ""
        async for chunk in self.generate_stream(messages, tools):
            if isinstance(chunk, str):
                full_text += chunk
            elif isinstance(chunk, dict):
                return chunk  # tool call — caller handles
        return full_text
```

---

### Step 3: Sarvam ASR client

**Create `app/pipeline/sarvam_asr.py`:**

```python
import httpx
import base64
from app.config import settings

class SarvamASR:
    """Sarvam AI Saaras v3 — streaming speech-to-text, 22 Indian languages."""

    BASE_URL = "https://api.sarvam.ai/speech-to-text"

    async def transcribe(self, audio_bytes: bytes, language_code: str = "unknown") -> dict:
        """
        Transcribe audio chunk.
        Returns: {"transcript": str, "language_code": str}
        """
        audio_b64 = base64.b64encode(audio_bytes).decode()
        payload = {
            "model": "saaras:v3",
            "audio": audio_b64,
            "language_code": language_code,
            "with_timestamps": False,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.BASE_URL,
                json=payload,
                headers={"api-subscription-key": settings.sarvam_api_key},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "transcript": data.get("transcript", ""),
                "language_code": data.get("language_code", language_code),
            }
```

---

### Step 4: Sarvam TTS client

**Create `app/pipeline/sarvam_tts.py`:**

```python
import httpx
import base64
from app.config import settings

# Language code → Sarvam speaker mapping
LANGUAGE_SPEAKERS = {
    "hi-IN": "meera",      # Hindi
    "ta-IN": "pavithra",   # Tamil
    "te-IN": "arvind",     # Telugu
    "mr-IN": "aarohi",     # Marathi
    "kn-IN": "suresh",     # Kannada
    "bn-IN": "riya",       # Bengali
    "default": "meera",
}

class SarvamTTS:
    """Sarvam AI Bulbul v3 — streaming text-to-speech, natural Indian voices."""

    BASE_URL = "https://api.sarvam.ai/text-to-speech"

    async def synthesize(self, text: str, language_code: str = "hi-IN") -> bytes:
        """
        Convert text to speech audio (PCM 8kHz).
        Returns raw audio bytes.
        """
        speaker = LANGUAGE_SPEAKERS.get(language_code, LANGUAGE_SPEAKERS["default"])
        payload = {
            "inputs": [text],
            "target_language_code": language_code,
            "speaker": speaker,
            "pitch": 0,
            "pace": 0.9,   # Slightly slower for rural clarity
            "loudness": 1.5,
            "speech_sample_rate": 8000,
            "enable_preprocessing": True,
            "model": "bulbul:v1",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.BASE_URL,
                json=payload,
                headers={"api-subscription-key": settings.sarvam_api_key},
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            audio_b64 = data["audios"][0]
            return base64.b64decode(audio_b64)
```

---

### Step 5: Voice pipeline orchestrator

**Create `app/pipeline/pipeline.py`:**

```python
import asyncio
import json
import re
from typing import AsyncGenerator
from app.pipeline.nova_client import NovaClient
from app.pipeline.sarvam_asr import SarvamASR
from app.pipeline.sarvam_tts import SarvamTTS

# Filler phrases — played immediately after ASR while Nova is thinking
# Gives ~400ms head start on audio delivery
FILLERS = {
    "hi-IN": "Haan ji, ek second...",
    "ta-IN": "Sari, oru nimidam...",
    "te-IN": "Avunu, okka nimisham...",
    "mr-IN": "Ho, ek kshan...",
    "kn-IN": "Haan, ondu nimisha...",
    "bn-IN": "Haan, ek moment...",
    "default": "One moment please...",
}

# Split on sentence-ending punctuation (including Hindi danda ।)
SENTENCE_SPLIT = re.compile(r'(?<=[।.!?])\s+')

class VoicePipeline:
    def __init__(self):
        self.asr = SarvamASR()
        self.nova = NovaClient()
        self.tts = SarvamTTS()

    async def _stream_tts_sentences(
        self, text_stream: AsyncGenerator, language_code: str
    ) -> AsyncGenerator[bytes, None]:
        """
        Consume a streaming text generator, split into sentences,
        and yield TTS audio chunks as each sentence completes.
        Achieves sentence-level streaming: audio starts before Nova finishes.
        """
        buffer = ""
        async for chunk in text_stream:
            buffer += chunk
            # Check if buffer contains a complete sentence
            parts = SENTENCE_SPLIT.split(buffer, maxsplit=1)
            while len(parts) > 1:
                sentence = parts[0].strip()
                buffer = parts[1]
                if sentence:
                    audio = await self.tts.synthesize(sentence, language_code)
                    yield audio
                parts = SENTENCE_SPLIT.split(buffer, maxsplit=1)

        # Flush remaining buffer
        if buffer.strip():
            audio = await self.tts.synthesize(buffer.strip(), language_code)
            yield audio

    async def process_turn(
        self,
        audio_bytes: bytes,
        farmer_profile: dict,
        conversation_history: list,
        language_code: str = "unknown",
        tools: list = None,
        tool_executor=None,
        audio_send_callback=None,  # async fn(bytes) → sends audio to WebSocket
    ) -> tuple[str, str]:
        """
        Process one voice turn with streaming latency optimizations.
        Returns: (transcript, detected_language)
        Audio is sent incrementally via audio_send_callback as it becomes available.
        """
        # ── Step 1: ASR ──────────────────────────────────────────────────────
        asr_result = await self.asr.transcribe(audio_bytes, language_code)
        transcript = asr_result["transcript"]
        detected_lang = asr_result["language_code"]

        if not transcript.strip():
            return "", detected_lang

        # ── Step 2: Filler phrase ─────────────────────────────────────────────
        # Send immediately — farmer hears something while Nova thinks
        filler_text = FILLERS.get(detected_lang, FILLERS["default"])
        filler_audio = await self.tts.synthesize(filler_text, detected_lang)
        if audio_send_callback:
            await audio_send_callback(filler_audio)

        # ── Step 3: Build message history ────────────────────────────────────
        messages = list(conversation_history)
        content = transcript
        if not messages and farmer_profile:
            content += f"\n\n[Farmer Profile: {json.dumps(farmer_profile)}]"
        messages.append({"role": "user", "content": [{"text": content}]})

        # ── Step 4: Stream Nova → sentence TTS ───────────────────────────────
        full_response = ""
        tool_called = None

        async def text_generator():
            nonlocal tool_called
            async for chunk in self.nova.generate_stream(messages, tools):
                if isinstance(chunk, str):
                    yield chunk
                elif isinstance(chunk, dict) and chunk.get("toolUse"):
                    tool_called = chunk["toolUse"]

        # Stream sentences to TTS as Nova generates them
        async for audio_chunk in self._stream_tts_sentences(
            text_generator(), detected_lang
        ):
            full_response += ""  # text tracked separately
            if audio_send_callback:
                await audio_send_callback(audio_chunk)

        # ── Step 5: Handle tool call (if any) ────────────────────────────────
        if tool_called and tool_executor:
            tool_result = await tool_executor(tool_called["name"], tool_called["input"])

            # Feed tool result back to Nova (non-streaming — short follow-up)
            conversation_history.append(
                {"role": "assistant", "content": [{"toolUse": tool_called}]}
            )
            conversation_history.append({
                "role": "user",
                "content": [{"toolResult": {
                    "toolUseId": tool_called["toolUseId"],
                    "content": [{"text": json.dumps(tool_result)}],
                }}]
            })
            follow_up = await self.nova.generate(
                user_text="", farmer_profile=farmer_profile,
                conversation_history=conversation_history,
            )
            if isinstance(follow_up, str) and follow_up.strip():
                # Stream follow-up TTS sentence by sentence too
                async def followup_gen():
                    for sentence in SENTENCE_SPLIT.split(follow_up):
                        if sentence.strip():
                            yield sentence + " "
                async for audio_chunk in self._stream_tts_sentences(
                    followup_gen(), detected_lang
                ):
                    if audio_send_callback:
                        await audio_send_callback(audio_chunk)

        # Update conversation history
        conversation_history.append(
            {"role": "user", "content": [{"text": transcript}]}
        )

        return transcript, detected_lang
```

---

### Step 6: WebSocket voice endpoint

**Create `app/routers/voice.py`:**

```python
import json
import base64
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.pipeline.pipeline import VoicePipeline
from app.tools.registry import NOVA_TOOLS, execute_tool

router = APIRouter(tags=["voice"])
pipeline = VoicePipeline()

@router.websocket("/ws/voice/{call_sid}")
async def voice_websocket(call_sid: str, ws: WebSocket, db: AsyncSession = Depends(get_db)):
    await ws.accept()

    conversation_history = []
    language_code = "unknown"
    farmer_profile = {}
    audio_buffer = bytearray()

    async def send_audio(audio_bytes: bytes):
        """Stream audio chunk back to Exotel over WebSocket."""
        await ws.send_text(json.dumps({
            "event": "media",
            "media": {"payload": base64.b64encode(audio_bytes).decode()}
        }))

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            if msg.get("event") == "media":
                chunk = base64.b64decode(msg["media"]["payload"])
                audio_buffer.extend(chunk)

            elif msg.get("event") == "stop" or len(audio_buffer) > 32000:
                if audio_buffer:
                    transcript, detected_lang = await pipeline.process_turn(
                        bytes(audio_buffer),
                        farmer_profile,
                        conversation_history,
                        language_code,
                        tools=NOVA_TOOLS,
                        tool_executor=execute_tool,
                        audio_send_callback=send_audio,  # ← incremental audio send
                    )
                    language_code = detected_lang
                    audio_buffer.clear()

    except WebSocketDisconnect:
        pass
```

---

### Step 7: Register routers in main.py

**Edit `app/main.py`:**

```python
from app.routers import voice
app.include_router(voice.router)
```

---

### Step 8: Run Nova test

```bash
pytest tests/test_nova.py -v
```

Expected: 2 PASSED

---

### Step 9: Commit

```bash
git add app/pipeline/ app/routers/voice.py tests/test_nova.py
git commit -m "feat: voice pipeline — Sarvam ASR + Nova Lite streaming + sentence TTS + filler phrases"
```

---

## Language Validation Note (Tamil)

After integration, run this manual test:
```python
# Send Tamil text directly to Nova and check response quality
from app.pipeline.nova_client import NovaClient
import asyncio

async def test_tamil():
    client = NovaClient()
    response = await client.generate(
        "Jaipur mandi il tomato vilai enna?",  # Tamil: What is tomato price in Jaipur mandi?
        farmer_profile={"language": "ta-IN", "state": "Tamil Nadu"}
    )
    print("Tamil response:", response)
    # Validate: response should be in Tamil, not English

asyncio.run(test_tamil())
```

Log result in `impl/language-validation.md`.

---

## Done when:
- [ ] `tests/test_nova.py` passes (model_id == `amazon.nova-lite-v1:0`)
- [ ] WebSocket endpoint sends audio incrementally (not all at once at end)
- [ ] Filler phrase is audible before Nova response arrives
- [ ] Pipeline correctly routes ASR → Nova stream → sentence TTS → audio
- [ ] Tamil test logged in `impl/language-validation.md`
