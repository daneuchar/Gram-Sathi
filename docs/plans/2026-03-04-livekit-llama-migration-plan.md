# LiveKit Agents + Llama 3.3 70B Migration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace FastRTC + Nova Lite with LiveKit Agents + Llama 3.3 70B (Bedrock), keeping Sarvam AI for STT/TTS.

**Architecture:** LiveKit Agents `VoicePipelineAgent` orchestrates the pipeline. STT uses the built-in `livekit.plugins.sarvam.STT` (streaming saaras:v3). LLM uses a custom `BedrockLLM` plugin (Llama 3.3 70B via Bedrock Converse API). TTS uses a thin custom wrapper that translates English→farmer's language then calls `livekit.plugins.sarvam.TTS`. A separate LiveKit worker process registers with LiveKit server; the FastAPI app stays for dashboard/webhooks.

**Tech Stack:** `livekit-agents[sarvam,silero,turn-detector]~=1.4`, `boto3` (already present), Sarvam AI, AWS Bedrock (`us.meta.llama3-3-70b-instruct-v1:0`)

**Design doc:** `docs/plans/2026-03-04-livekit-llama-migration-design.md`

---

## Task 1: Install LiveKit Agents and verify environment

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add livekit-agents to dependencies**

In `pyproject.toml`, add to the `[project] dependencies` list:
```
"livekit-agents[sarvam,silero,turn-detector]~=1.4",
"livekit-api~=1.0",
```

**Step 2: Install**

```bash
uv pip install "livekit-agents[sarvam,silero,turn-detector]~=1.4" "livekit-api~=1.0"
```

Expected: No errors. Packages installed successfully.

**Step 3: Verify import**

```bash
python -c "from livekit.agents import Agent, AgentSession, JobContext; from livekit.plugins import sarvam, silero; print('OK')"
```

Expected: prints `OK`

**Step 4: Add LiveKit config to `src/app/config.py`**

Add these fields to the `Settings` class (after the existing fields):
```python
# LiveKit
livekit_url: str = ""           # e.g. wss://my-app.livekit.cloud
livekit_api_key: str = ""
livekit_api_secret: str = ""

# Llama 3.3 70B on Bedrock
llama_model_id: str = "us.meta.llama3-3-70b-instruct-v1:0"
```

**Step 5: Commit**

```bash
git add pyproject.toml src/app/config.py
git commit -m "feat: add livekit-agents dependency and config"
```

---

## Task 2: Write the BedrockLLM plugin (TDD)

**Files:**
- Create: `src/app/plugins/__init__.py` (empty)
- Create: `src/app/plugins/bedrock_llm.py`
- Create: `src/tests/plugins/test_bedrock_llm.py`

**Background:** `livekit.agents.llm.LLM` requires implementing a `chat()` method that returns an `LLMStream`. The stream is an async iterator yielding `ChatChunk` objects. Bedrock Converse API is synchronous (boto3), so we run it in an executor and yield the final response as a single chunk. Tool calls are handled inline (same loop as current Nova client).

**Step 1: Write the failing test**

Create `src/tests/plugins/test_bedrock_llm.py`:

```python
"""Tests for BedrockLLM plugin."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from livekit.agents import llm


def make_bedrock_response(text: str) -> dict:
    """Build a minimal Bedrock Converse API response dict."""
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": text}],
            }
        },
        "stopReason": "end_turn",
    }


@pytest.mark.asyncio
async def test_bedrock_llm_basic_response():
    """BedrockLLM.chat() yields a ChatChunk with the model's text."""
    from app.plugins.bedrock_llm import BedrockLLM

    mock_response = make_bedrock_response("Wheat price is one thousand rupees.")

    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.converse.return_value = mock_response

        llm_plugin = BedrockLLM()
        chat_ctx = llm.ChatContext().append(role="user", text="What is the wheat price?")

        chunks = []
        async with llm_plugin.chat(chat_ctx=chat_ctx) as stream:
            async for chunk in stream:
                if chunk.delta and chunk.delta.text:
                    chunks.append(chunk.delta.text)

        assert "".join(chunks) == "Wheat price is one thousand rupees."


@pytest.mark.asyncio
async def test_bedrock_llm_system_prompt_injection():
    """BedrockLLM uses system prompt from chat context or falls back to default."""
    from app.plugins.bedrock_llm import BedrockLLM

    mock_response = make_bedrock_response("Namaste Ramesh!")

    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.converse.return_value = mock_response

        llm_plugin = BedrockLLM()
        chat_ctx = (
            llm.ChatContext()
            .append(role="system", text="Custom system prompt.")
            .append(role="user", text="Hello")
        )

        async with llm_plugin.chat(chat_ctx=chat_ctx) as stream:
            async for _ in stream:
                pass

        call_kwargs = mock_client.converse.call_args[1]
        assert call_kwargs["system"][0]["text"] == "Custom system prompt."
```

**Step 2: Run to verify it fails**

```bash
cd /Users/danieleuchar/workspace/gramvaani
python -m pytest src/tests/plugins/test_bedrock_llm.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'app.plugins.bedrock_llm'`

**Step 3: Create `src/app/plugins/__init__.py`**

Empty file:
```python
```

**Step 4: Implement `src/app/plugins/bedrock_llm.py`**

```python
"""AWS Bedrock LLM plugin for LiveKit Agents — uses Llama 3.3 70B via Converse API."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator

import boto3
from livekit.agents import llm
from livekit.agents.llm import ChatChunk, ChoiceDelta

from app.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are Gram Saathi, a helpful voice assistant for Indian farmers.

Language:
- Always respond in English. The system will translate to the farmer's language.
- Use simple, clear spoken English suitable for phone conversations.

Response Style:
- This is a PHONE CALL. Keep every response to ONE or TWO short sentences maximum.
- Never explain, elaborate, or add follow-up offers. Answer only what was asked.
- Never use markdown formatting — no asterisks, bullet points, headers, or symbols. Plain text only.

Accuracy:
- Always use available tools for real-time data such as prices, weather, or government schemes.
- Never guess or fabricate factual information.
- If data is unavailable, say: "That information is not available right now."
- If outside farming topics, say: "I can only help with farming questions."

Number Formatting:
- Always spell out numbers in English words.
- Say "twelve hundred rupees" not "1200 rupees". Say "twenty five percent" not "25%".

Tone:
- Be polite, supportive, and respectful to farmers.
"""


class _BedrockLLMStream(llm.LLMStream):
    """Wraps a Bedrock Converse call as a LiveKit LLMStream."""

    def __init__(
        self,
        llm_instance: "BedrockLLM",
        chat_ctx: llm.ChatContext,
        fnc_ctx: llm.FunctionContext | None,
    ) -> None:
        super().__init__(llm_instance, chat_ctx=chat_ctx, fnc_ctx=fnc_ctx)
        self._llm = llm_instance
        self._chat_ctx = chat_ctx

    async def _run(self) -> None:
        messages, system = _build_bedrock_messages(self._chat_ctx)
        kwargs: dict = {
            "modelId": settings.llama_model_id,
            "system": [{"text": system}],
            "messages": messages,
            "inferenceConfig": {"maxTokens": 256, "temperature": 0.3},
        }

        # Tool calling support
        if self._fnc_ctx and self._fnc_ctx.ai_functions:
            kwargs["toolConfig"] = {"tools": _build_tool_config(self._fnc_ctx)}

        for _ in range(5):  # max tool rounds
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda k=kwargs: self._llm._client.converse(**k)
            )
            output_msg = response.get("output", {}).get("message", {})
            parts = output_msg.get("content", [])
            stop_reason = response.get("stopReason", "end_turn")

            tool_uses = [p for p in parts if "toolUse" in p]
            if tool_uses and self._fnc_ctx:
                # Execute tools and continue
                messages.append({"role": "assistant", "content": parts})
                tool_results = []
                for block in tool_uses:
                    tu = block["toolUse"]
                    fn = self._fnc_ctx.ai_functions.get(tu["name"])
                    if fn:
                        result = await fn(**tu["input"])
                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tu["toolUseId"],
                                "content": [{"json": result}],
                            }
                        })
                messages.append({"role": "user", "content": tool_results})
                kwargs["messages"] = messages
            else:
                text = " ".join(p["text"] for p in parts if "text" in p)
                self._event_ch.send_nowait(
                    ChatChunk(
                        request_id=self.request_id,
                        choices=[ChoiceDelta(role="assistant", content=text)],
                    )
                )
                return


class BedrockLLM(llm.LLM):
    """LiveKit LLM plugin backed by AWS Bedrock (Llama 3.3 70B)."""

    def __init__(self) -> None:
        super().__init__()
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_default_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        fnc_ctx: llm.FunctionContext | None = None,
    ) -> _BedrockLLMStream:
        return _BedrockLLMStream(self, chat_ctx=chat_ctx, fnc_ctx=fnc_ctx)


def _build_bedrock_messages(chat_ctx: llm.ChatContext) -> tuple[list[dict], str]:
    """Convert LiveKit ChatContext to Bedrock Converse messages + system string."""
    system = _SYSTEM_PROMPT
    messages: list[dict] = []

    for msg in chat_ctx.messages:
        if msg.role == "system":
            system = msg.content or _SYSTEM_PROMPT
            continue
        role = "user" if msg.role == "user" else "assistant"
        text = msg.content or ""
        messages.append({"role": role, "content": [{"text": text}]})

    return messages, system


def _build_tool_config(fnc_ctx: llm.FunctionContext) -> list[dict]:
    """Convert LiveKit FunctionContext to Bedrock toolConfig tools list."""
    tools = []
    for name, fn in fnc_ctx.ai_functions.items():
        tools.append({
            "toolSpec": {
                "name": name,
                "description": fn.metadata.description or "",
                "inputSchema": {"json": fn.metadata.raw_schema},
            }
        })
    return tools
```

**Step 5: Run tests**

```bash
python -m pytest src/tests/plugins/test_bedrock_llm.py -v
```

Expected: Both tests PASS.

**Step 6: Commit**

```bash
git add src/app/plugins/ src/tests/plugins/
git commit -m "feat: add BedrockLLM plugin for Llama 3.3 70B"
```

---

## Task 3: Write the SarvamTTS wrapper (TDD)

**Files:**
- Create: `src/app/plugins/sarvam_tts_wrapper.py`
- Create: `src/tests/plugins/test_sarvam_tts_wrapper.py`

**Background:** `livekit.plugins.sarvam.TTS` fixes `target_language_code` at construction time — it cannot change per-call. Since language changes per-farmer at runtime, we need a custom TTS plugin. The wrapper:
- Implements `livekit.agents.tts.TTS` using our existing `synthesize_streaming()` from `sarvam_tts.py`
- Has a mutable `language` attribute updated by `before_tts_cb` before each turn
- `before_tts_cb` handles text pre-processing: strip markdown → expand numbers → translate English→farmer's language, then sets `tts.language` before synthesis

This file (`sarvam_tts_wrapper.py`) provides the `prepare_tts_text()` utility used by `before_tts_cb`.

**Step 1: Write the failing test**

Create `src/tests/plugins/test_sarvam_tts_wrapper.py`:

```python
"""Tests for SarvamTTS pre-processing utilities."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_prepare_tts_text_strips_markdown():
    from app.plugins.sarvam_tts_wrapper import prepare_tts_text

    result = await prepare_tts_text("**Price is 1200 rupees**", "en-IN")
    assert "*" not in result
    assert "twelve hundred" in result


@pytest.mark.asyncio
async def test_prepare_tts_text_translates_for_hindi():
    from app.plugins.sarvam_tts_wrapper import prepare_tts_text

    with patch("app.plugins.sarvam_tts_wrapper.from_english", new_callable=AsyncMock) as mock_trans:
        mock_trans.return_value = "गेहूं की कीमत बारह सौ रुपये है"
        result = await prepare_tts_text("Wheat price is 1200 rupees", "hi-IN")

    mock_trans.assert_called_once()
    assert result == "गेहूं की कीमत बारह सौ रुपये है"


@pytest.mark.asyncio
async def test_prepare_tts_text_skips_translate_for_english():
    from app.plugins.sarvam_tts_wrapper import prepare_tts_text

    with patch("app.plugins.sarvam_tts_wrapper.from_english", new_callable=AsyncMock) as mock_trans:
        result = await prepare_tts_text("Hello farmer", "en-IN")

    mock_trans.assert_not_called()
    assert result == "Hello farmer"
```

**Step 2: Run to verify it fails**

```bash
python -m pytest src/tests/plugins/test_sarvam_tts_wrapper.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'app.plugins.sarvam_tts_wrapper'`

**Step 3: Implement `src/app/plugins/sarvam_tts_wrapper.py`**

```python
"""Pre-processing utilities for Sarvam TTS — markdown strip, number expansion, translation."""
from __future__ import annotations

import re

from app.pipeline.sarvam_translate import from_english, ENGLISH_LANGS

_MARKDOWN_RE = re.compile(r'[*_`#~>]+')
_MARKER_RE = re.compile(r'<<<[^>]*>>>')
_NUMBER_RE = re.compile(r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b|\b\d+(?:\.\d+)?\b')


def _strip_markdown(text: str) -> str:
    text = _MARKER_RE.sub('', text)
    text = _MARKDOWN_RE.sub('', text)
    return text.strip()


def _expand_numbers(text: str) -> str:
    from num2words import num2words
    def _replace(m: re.Match) -> str:
        raw = m.group().replace(",", "")
        try:
            n = float(raw)
            return num2words(int(n) if n == int(n) else n, lang="en")
        except Exception:
            return m.group()
    return _NUMBER_RE.sub(_replace, text)


async def prepare_tts_text(text: str, language_code: str) -> str:
    """Strip markdown, expand numbers, translate to farmer's language if needed."""
    text = _strip_markdown(text)
    text = _expand_numbers(text)
    if language_code not in ENGLISH_LANGS:
        text = await from_english(text, language_code)
    return text
```

**Step 4: Run tests**

```bash
python -m pytest src/tests/plugins/test_sarvam_tts_wrapper.py -v
```

Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
git add src/app/plugins/sarvam_tts_wrapper.py src/tests/plugins/test_sarvam_tts_wrapper.py
git commit -m "feat: add SarvamTTS pre-processing (strip markdown, expand numbers, translate)"
```

---

## Task 4: Write the agent entrypoint (TDD)

**Files:**
- Create: `src/app/livekit_agent.py`
- Create: `src/tests/test_livekit_agent.py`

**Background:** This is the main agent entry point. `entrypoint(ctx)` is called by LiveKit when a new call comes in. It creates an `AgentSession` with STT/LLM/TTS/turn-detection, attaches `before_tts_cb` for translation, starts the agent. Farmer profile is loaded from DB via phone number (from room metadata). Onboarding vs returning farmer is determined by whether a profile exists. The `PROFILE` marker extraction from Nova client is reused here.

**Step 1: Write the failing test**

Create `src/tests/test_livekit_agent.py`:

```python
"""Tests for LiveKit agent entrypoint helpers."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_build_system_prompt_with_profile():
    from app.livekit_agent import build_system_prompt

    profile = {"name": "Ramesh", "state": "Punjab", "district": "Ludhiana"}
    prompt = build_system_prompt(profile)

    assert "Ramesh" in prompt
    assert "Punjab" in prompt
    assert "Ludhiana" in prompt


def test_build_system_prompt_no_profile_returns_onboarding():
    from app.livekit_agent import build_system_prompt
    from app.pipeline.nova_client import ONBOARDING_PROMPT

    prompt = build_system_prompt(None)
    assert prompt == ONBOARDING_PROMPT


@pytest.mark.asyncio
async def test_before_tts_cb_translates_text():
    from app.livekit_agent import make_before_tts_cb

    session_data = {"language": "hi-IN"}

    with patch("app.livekit_agent.prepare_tts_text", new_callable=AsyncMock) as mock_prep:
        mock_prep.return_value = "गेहूं की कीमत बारह सौ रुपये है"
        cb = make_before_tts_cb(session_data)
        agent_mock = MagicMock()
        result = await cb(agent_mock, "Wheat price is twelve hundred rupees")

    mock_prep.assert_called_once_with("Wheat price is twelve hundred rupees", "hi-IN")
    assert result == "गेहूं की कीमत बारह सौ रुपये है"
```

**Step 2: Run to verify it fails**

```bash
python -m pytest src/tests/test_livekit_agent.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'app.livekit_agent'`

**Step 3: Implement `src/app/livekit_agent.py`**

```python
"""LiveKit Agents entrypoint for Gram Saathi."""
from __future__ import annotations

import logging
import re

from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli
from livekit.agents.voice import VoicePipelineAgent
from livekit.plugins import sarvam, silero
from livekit.plugins.turn_detector import MultilingualModel

from app.config import settings
from app.database import get_farmer_by_phone, save_farmer_profile
from app.pipeline.nova_client import ONBOARDING_PROMPT, SYSTEM_PROMPT, extract_profile_marker
from app.plugins.bedrock_llm import BedrockLLM
from app.plugins.sarvam_tts_wrapper import prepare_tts_text
from app.tools.registry import NOVA_TOOLS, execute_tool

logger = logging.getLogger(__name__)

_PROFILE_RE = re.compile(r'<<<PROFILE:(\{.*?\})>>>')


def build_system_prompt(profile: dict | None) -> str:
    """Return main system prompt with profile context, or onboarding prompt."""
    if profile is None:
        return ONBOARDING_PROMPT
    name = profile.get("name", "")
    state = profile.get("state", "")
    district = profile.get("district", "")
    profile_ctx = (
        f"Farmer profile — Name: {name}, State: {state}, District: {district}. "
        f"Greet them warmly by name on the first turn. "
        f"Default weather and mandi queries to {state}, {district}."
    )
    return SYSTEM_PROMPT + "\n\n" + profile_ctx


def make_before_tts_cb(session_data: dict):
    """Return a before_tts_cb that translates English text to the farmer's language."""
    async def before_tts(agent, text: str) -> str:
        lang = session_data.get("language", "en-IN")
        return await prepare_tts_text(text, lang)
    return before_tts


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    # Resolve farmer profile from phone number (passed in room metadata by SIP gateway)
    phone = ctx.room.metadata or ""
    profile = await get_farmer_by_phone(phone) if phone else None
    language = profile.get("language", "en-IN") if profile else "en-IN"

    session_data: dict = {
        "profile": profile,
        "language": language,
        "phone": phone,
    }

    # STT: Sarvam saaras:v3 streaming (built-in LiveKit plugin)
    stt = sarvam.STT(
        model="saaras:v3",
        mode="translate" if language != "en-IN" else "transcribe",
        language_code=language if profile else None,  # None = auto-detect during onboarding
        api_key=settings.sarvam_api_key,
    )

    # TTS: Sarvam bulbul (built-in LiveKit plugin, language set dynamically via before_tts_cb)
    tts = sarvam.TTS(
        model="bulbul:v1",
        target_language_code=language,
        api_key=settings.sarvam_api_key,
    )

    session = AgentSession(
        stt=stt,
        llm=BedrockLLM(),
        tts=tts,
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
        before_tts_cb=make_before_tts_cb(session_data),
    )

    # Handle PROFILE marker from onboarding — save to DB and update session
    @session.on("agent_message_committed")
    async def on_agent_message(message):
        profile_data, _ = extract_profile_marker(message.content or "")
        if profile_data and not session_data.get("profile"):
            await save_farmer_profile(phone, profile_data)
            session_data["profile"] = profile_data
            session_data["language"] = profile_data.get("language", "en-IN")
            logger.info("[onboarding] profile saved for %s: %s", phone, profile_data)

    agent = VoicePipelineAgent(
        session=session,
        chat_ctx=Agent(instructions=build_system_prompt(profile)),
    )
    agent.start(ctx.room)
    await session.wait_for_disconnect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
```

**Step 4: Run tests**

```bash
python -m pytest src/tests/test_livekit_agent.py -v
```

Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
git add src/app/livekit_agent.py src/tests/test_livekit_agent.py
git commit -m "feat: add LiveKit agent entrypoint with BedrockLLM and Sarvam plugins"
```

---

## Task 5: Update main.py — remove FastRTC, add LiveKit dispatch webhook

**Files:**
- Modify: `src/app/main.py`

**Background:** FastRTC (`Stream`, `gr.mount_gradio_app`) is replaced by the LiveKit worker process. Keep FastAPI for the dashboard. Add a LiveKit dispatch webhook endpoint so LiveKit SIP calls can be routed to the agent.

**Step 1: Read current `src/app/main.py`** (already done in context)

**Step 2: Replace `src/app/main.py`**

```python
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request, Response
from livekit.api import LiveKitAPI, CreateRoomRequest

from app.config import settings
from app.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Gram Saathi API", version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "gram-saathi"}


from app.routers import webhooks, dashboard
app.include_router(webhooks.router)
app.include_router(dashboard.router)
```

**Step 3: Verify the app starts**

```bash
cd /Users/danieleuchar/workspace/gramvaani
python -m uvicorn app.main:app --port 8000 2>&1 | head -10
```

Expected: `INFO: Application startup complete.` (no errors about missing FastRTC/gradio imports)

**Step 4: Run existing tests to check nothing broke**

```bash
python -m pytest src/tests/ -v --ignore=src/tests/test_e2e_voice_flow.py -x
```

Expected: All tests PASS (or pre-existing failures only).

**Step 5: Commit**

```bash
git add src/app/main.py
git commit -m "feat: remove FastRTC, update main.py for LiveKit worker architecture"
```

---

## Task 6: Configure LiveKit SIP telephony

**Files:**
- No code changes — this is configuration

**Background:** We switch from Twilio Media Streams (WebSocket) to Twilio SIP Trunk → LiveKit SIP. LiveKit receives the SIP call, creates a Room, and dispatches a job to the agent worker.

**Step 1: Get LiveKit credentials**

Option A (LiveKit Cloud — easiest):
1. Sign up at https://cloud.livekit.io
2. Create a project
3. Copy: `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`

Option B (self-hosted): Run LiveKit server via Docker — see https://docs.livekit.io/home/self-hosting/local/

Add to `.env`:
```
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_key
LIVEKIT_API_SECRET=your_secret
```

**Step 2: Enable LiveKit SIP**

In LiveKit Cloud dashboard → SIP → Create Inbound Trunk:
- Trunk name: `gram-saathi-inbound`
- Note the SIP URI (e.g. `sip:xxx@sip.livekit.cloud`)

**Step 3: Configure Twilio SIP Trunk**

In Twilio Console → Elastic SIP Trunking:
1. Create a SIP Trunk
2. Origination → add LiveKit SIP URI as the origination SIP URI
3. Phone numbers → attach your existing Twilio number to this trunk

Result: Incoming calls to your Twilio number → LiveKit SIP → LiveKit Room → agent worker

**Step 4: Test with a local worker**

```bash
LIVEKIT_URL=wss://... LIVEKIT_API_KEY=... LIVEKIT_API_SECRET=... \
  python -m app.livekit_agent
```

Expected: `Connected to LiveKit server. Waiting for jobs...`

---

## Task 7: Filler audio via before_llm_cb

**Files:**
- Modify: `src/app/livekit_agent.py`

**Background:** The current pipeline plays context-aware filler audio (0ms latency, pre-recorded) while the LLM warms up. In LiveKit, `before_llm_cb` is called with the transcript before LLM inference. We push filler audio frames through the agent's audio output.

**Step 1: Write the failing test**

Add to `src/tests/test_livekit_agent.py`:

```python
def test_classify_filler_mandi():
    from app.livekit_agent import classify_filler_for_transcript
    assert classify_filler_for_transcript("what is the wheat price in mandi") == "mandi"

def test_classify_filler_generic():
    from app.livekit_agent import classify_filler_for_transcript
    assert classify_filler_for_transcript("tell me something about farming") == "generic"

def test_classify_filler_none_for_short():
    from app.livekit_agent import classify_filler_for_transcript
    assert classify_filler_for_transcript("ok") == "none"
```

**Step 2: Run to verify they fail**

```bash
python -m pytest src/tests/test_livekit_agent.py::test_classify_filler_mandi -v
```

Expected: `ImportError: cannot import name 'classify_filler_for_transcript'`

**Step 3: Add `classify_filler_for_transcript` and `make_before_llm_cb` to `livekit_agent.py`**

Import the existing keywords from `pipeline.py` (or copy them — pipeline.py will be retired):

```python
# Add near top of livekit_agent.py
from app.pipeline.sarvam_tts import get_filler_audio

_MANDI_KW = {'price', 'rate', 'mandi', 'market', 'cost', 'tomato', 'onion',
             'wheat', 'rice', 'potato', 'cotton', 'maize', 'soybean', 'groundnut'}
_WEATHER_KW = {'weather', 'rain', 'rainfall', 'forecast', 'temperature',
               'wind', 'storm', 'cloud', 'sunny', 'hot', 'cold', 'humid', 'monsoon'}
_SCHEME_KW = {'scheme', 'subsidy', 'government', 'kisan', 'eligible',
              'benefit', 'loan', 'insurance', 'fasal', 'yojana'}
_QUESTION_WORDS = {'what', 'when', 'where', 'who', 'why', 'how', 'which',
                   'is', 'are', 'will', 'can', 'do', 'does'}


def classify_filler_for_transcript(transcript: str) -> str:
    words = transcript.lower().split()
    word_set = set(words)
    if word_set & _MANDI_KW:
        return 'mandi'
    if word_set & _WEATHER_KW:
        return 'weather'
    if word_set & _SCHEME_KW:
        return 'scheme'
    if len(words) <= 4 and '?' not in transcript and not (word_set & _QUESTION_WORDS):
        return 'none'
    return 'generic'


def make_before_llm_cb(session_data: dict):
    async def before_llm(agent, chat_ctx) -> None:
        # Get the last user message as transcript
        transcript = ""
        for msg in reversed(chat_ctx.messages):
            if msg.role == "user":
                transcript = msg.content or ""
                break
        category = classify_filler_for_transcript(transcript)
        lang = session_data.get("language", "en-IN")
        filler = get_filler_audio(lang, category, sample_rate=8000)
        if filler:
            await agent.say(filler, allow_interruptions=False)
    return before_llm
```

Then update the `AgentSession` creation in `entrypoint()` to add:
```python
before_llm_cb=make_before_llm_cb(session_data),
```

**Step 4: Run tests**

```bash
python -m pytest src/tests/test_livekit_agent.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/app/livekit_agent.py src/tests/test_livekit_agent.py
git commit -m "feat: add filler audio via before_llm_cb in LiveKit agent"
```

---

## Task 8: Retire old pipeline files

**Files:**
- Delete: `src/app/handlers/gram_saathi.py`
- Delete: `src/app/pipeline/pipeline.py`
- Delete: `src/app/pipeline/nova_client.py`
- Delete: `src/app/pipeline/openai_client.py`

**Step 1: Check for any remaining imports**

```bash
grep -r "from app.handlers.gram_saathi\|from app.pipeline.pipeline\|from app.pipeline.nova_client\|from app.pipeline.openai_client" src/ --include="*.py"
```

Expected: No output (zero references outside tests).

**Step 2: If any references remain**, update them to use the LiveKit equivalents before deleting.

**Step 3: Delete the files**

```bash
git rm src/app/handlers/gram_saathi.py \
       src/app/pipeline/pipeline.py \
       src/app/pipeline/nova_client.py \
       src/app/pipeline/openai_client.py
```

**Step 4: Run all tests**

```bash
python -m pytest src/tests/ -v --ignore=src/tests/test_e2e_voice_flow.py
```

Expected: All PASS (e2e test skipped — it tests FastRTC directly).

**Step 5: Commit**

```bash
git commit -m "chore: retire FastRTC pipeline files — replaced by LiveKit agent"
```

---

## Task 9: End-to-end smoke test

**Step 1: Start the worker locally**

```bash
# Terminal 1 — FastAPI
uvicorn app.main:app --port 8000

# Terminal 2 — LiveKit worker
LIVEKIT_URL=wss://... LIVEKIT_API_KEY=... LIVEKIT_API_SECRET=... \
SARVAM_API_KEY=... AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... \
  python -m app.livekit_agent
```

**Step 2: Make a test call**

Call your Twilio number (now routed via SIP → LiveKit).

Expected flow:
1. LiveKit creates a Room
2. Agent worker picks up the job
3. Farmer hears Gram Saathi greeting
4. Farmer speaks in Hindi → saaras:v3 transcribes+translates to English
5. Llama 3.3 70B responds in English
6. bulbul:v3 speaks in Hindi

**Step 3: Verify logs show Llama 3.3 70B**

```
INFO — BedrockLLM: model=us.meta.llama3-3-70b-instruct-v1:0
INFO — [STT] transcript=... detected_lang=hi-IN
```

**Step 4: Commit**

No code changes — just document the result in a brief note or close this task.

---

## Summary of files changed

| File | Action |
|------|--------|
| `pyproject.toml` | Add livekit-agents deps |
| `src/app/config.py` | Add LiveKit + Llama config fields |
| `src/app/livekit_agent.py` | NEW — agent entrypoint |
| `src/app/plugins/__init__.py` | NEW — empty |
| `src/app/plugins/bedrock_llm.py` | NEW — Llama 3.3 70B plugin |
| `src/app/plugins/sarvam_tts_wrapper.py` | NEW — TTS pre-processing |
| `src/app/main.py` | Remove FastRTC, keep FastAPI |
| `src/app/handlers/gram_saathi.py` | DELETED |
| `src/app/pipeline/pipeline.py` | DELETED |
| `src/app/pipeline/nova_client.py` | DELETED |
| `src/app/pipeline/openai_client.py` | DELETED |
