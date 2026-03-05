# Farmer Onboarding Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When a new phone number connects via the web UI, collect name, state, and district through a natural Nova-driven voice conversation, auto-detect language, save the profile to the database, and switch to the normal agricultural assistant mode.

**Architecture:** A phone number `gr.Textbox` in the Gradio UI passes the phone to `GramSaathiHandler`. On first turn the handler queries the DB — new user (no name) gets an onboarding system prompt; returning user gets normal mode with profile injected as context. Handler scans Nova's response for a `<<<PROFILE:{...}>>>` marker, saves to DB, and switches mode.

**Tech Stack:** Python 3.12, FastRTC + Gradio, SQLAlchemy async, Amazon Bedrock Nova Lite, FastAPI.

---

### Task 1: DB helper functions — `get_or_create_user` and `update_user_profile`

**Files:**
- Modify: `src/app/database.py`
- Create: `src/tests/test_database_helpers.py`

**Context:**
- `AsyncSessionLocal` is already imported in `database.py`
- `User` model is at `src/app/models/user.py` with fields: `phone`, `name`, `state`, `district`, `language`
- New user = `user.name is None`

**Step 1: Write failing tests**

```python
# src/tests/test_database_helpers.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.database import get_or_create_user, update_user_profile


@pytest.mark.asyncio
async def test_get_or_create_user_new():
    mock_session = AsyncMock()
    mock_session.get.return_value = None  # user not found
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    with patch("app.database.AsyncSessionLocal") as mock_factory:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        user = await get_or_create_user("+919876543210")

    mock_session.add.assert_called_once()
    added = mock_session.add.call_args[0][0]
    assert added.phone == "+919876543210"
    assert added.name is None


@pytest.mark.asyncio
async def test_get_or_create_user_existing():
    from app.models.user import User
    existing = User(phone="+919876543210", name="Ramesh", state="Tamil Nadu")
    mock_session = AsyncMock()
    mock_session.get.return_value = existing

    with patch("app.database.AsyncSessionLocal") as mock_factory:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        user = await get_or_create_user("+919876543210")

    mock_session.add.assert_not_called()
    assert user.name == "Ramesh"


@pytest.mark.asyncio
async def test_update_user_profile():
    from app.models.user import User
    existing = User(phone="+919876543210")
    mock_session = AsyncMock()
    mock_session.get.return_value = existing
    mock_session.commit = AsyncMock()

    with patch("app.database.AsyncSessionLocal") as mock_factory:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        await update_user_profile("+919876543210", name="Ramesh", state="Tamil Nadu", district="Coimbatore", language="ta-IN")

    assert existing.name == "Ramesh"
    assert existing.state == "Tamil Nadu"
    assert existing.district == "Coimbatore"
    assert existing.language == "ta-IN"
    mock_session.commit.assert_called_once()
```

**Step 2: Run to confirm failure**

```bash
cd /Users/danieleuchar/workspace/gramvaani && PYTHONPATH=src uv run pytest src/tests/test_database_helpers.py -v
```

Expected: `ImportError` — `get_or_create_user` not defined yet.

**Step 3: Add helpers to `src/app/database.py`**

Append to the end of the file:

```python
from app.models.user import User


async def get_or_create_user(phone: str) -> User:
    """Load user by phone, creating a minimal record if not found."""
    async with AsyncSessionLocal() as session:
        user = await session.get(User, phone)
        if user is None:
            user = User(phone=phone)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user


async def update_user_profile(
    phone: str,
    *,
    name: str | None = None,
    state: str | None = None,
    district: str | None = None,
    language: str | None = None,
) -> None:
    """Update farmer profile fields. Only sets fields that are provided."""
    async with AsyncSessionLocal() as session:
        user = await session.get(User, phone)
        if user is None:
            return
        if name is not None:
            user.name = name
        if state is not None:
            user.state = state
        if district is not None:
            user.district = district
        if language is not None:
            user.language = language
        await session.commit()
```

**Step 4: Run tests**

```bash
cd /Users/danieleuchar/workspace/gramvaani && PYTHONPATH=src uv run pytest src/tests/test_database_helpers.py -v
```

Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
git add src/app/database.py src/tests/test_database_helpers.py
git commit -m "feat: add get_or_create_user and update_user_profile DB helpers"
```

---

### Task 2: Onboarding system prompt + PROFILE marker extraction

**Files:**
- Modify: `src/app/pipeline/nova_client.py`
- Create: `src/tests/test_onboarding_prompt.py`

**Context:**
- `SYSTEM_PROMPT` is a module-level constant in `nova_client.py`
- `_build_kwargs` always uses `SYSTEM_PROMPT` — we need it to accept an override
- The `<<<PROFILE:{"name":"...","state":"...","district":"..."}>>>` marker must be stripped from the spoken response

**Step 1: Write failing tests**

```python
# src/tests/test_onboarding_prompt.py
import pytest
from app.pipeline.nova_client import ONBOARDING_PROMPT, extract_profile_marker


def test_onboarding_prompt_exists():
    assert "<<<PROFILE:" in ONBOARDING_PROMPT
    assert "name" in ONBOARDING_PROMPT
    assert "state" in ONBOARDING_PROMPT
    assert "district" in ONBOARDING_PROMPT


def test_extract_profile_marker_found():
    response = 'Welcome! <<<PROFILE:{"name":"Ramesh","state":"Tamil Nadu","district":"Coimbatore"}>>> How can I help?'
    profile, clean = extract_profile_marker(response)
    assert profile == {"name": "Ramesh", "state": "Tamil Nadu", "district": "Coimbatore"}
    assert "<<<PROFILE:" not in clean
    assert "How can I help?" in clean


def test_extract_profile_marker_not_found():
    response = "Hello, how can I help you today?"
    profile, clean = extract_profile_marker(response)
    assert profile is None
    assert clean == response


def test_extract_profile_marker_strips_whitespace():
    response = "Great!  <<<PROFILE:{\"name\":\"Anita\",\"state\":\"Punjab\",\"district\":\"Ludhiana\"}>>>\n\nNamaste Anita!"
    profile, clean = extract_profile_marker(response)
    assert profile["name"] == "Anita"
    assert "Namaste Anita!" in clean.strip()
```

**Step 2: Run to confirm failure**

```bash
cd /Users/danieleuchar/workspace/gramvaani && PYTHONPATH=src uv run pytest src/tests/test_onboarding_prompt.py -v
```

Expected: `ImportError` — `ONBOARDING_PROMPT` and `extract_profile_marker` not defined yet.

**Step 3: Add to `src/app/pipeline/nova_client.py`**

Add after `SYSTEM_PROMPT` constant (around line 40):

```python
import json
import re

ONBOARDING_PROMPT = """
You are Gram Saathi, a voice assistant for Indian farmers.

This farmer is calling for the first time. Your job is to warmly welcome them and collect their profile in a natural conversation.

Instructions:
- Detect the language from their first utterance and respond in that same language throughout.
- Welcome them warmly, then ask for their name.
- After they give their name, ask for their state and district or village.
- Once you have name, state, and district, output this marker on its own line:
  <<<PROFILE:{"name":"<name>","state":"<state>","district":"<district>"}>>>
- Immediately after the marker, greet them by name and offer to help with farming questions.
- Keep responses short and spoken-friendly.
- Never use digits — spell out all numbers as words.
"""

_PROFILE_RE = re.compile(r'<<<PROFILE:(\{.*?\})>>>', re.DOTALL)


def extract_profile_marker(response: str) -> tuple[dict | None, str]:
    """Extract <<<PROFILE:{...}>>> from Nova response.

    Returns (profile_dict, cleaned_response).
    profile_dict is None if no marker found.
    """
    match = _PROFILE_RE.search(response)
    if not match:
        return None, response
    try:
        profile = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None, response
    clean = _PROFILE_RE.sub("", response).strip()
    return profile, clean
```

Also update `_build_kwargs` to accept an optional `system_prompt` override. Find `_build_kwargs` and change:

```python
    def _build_kwargs(
        self, messages: list[dict], tools: list[dict] | None
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "system": [{"text": SYSTEM_PROMPT}],
            "messages": messages,
            "inferenceConfig": {
                "maxTokens": 512,
                "temperature": 0.3,
            },
        }
        if tools:
            kwargs["toolConfig"] = {"tools": tools}
        return kwargs
```

To:

```python
    def _build_kwargs(
        self, messages: list[dict], tools: list[dict] | None, system_prompt: str | None = None
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "system": [{"text": system_prompt or SYSTEM_PROMPT}],
            "messages": messages,
            "inferenceConfig": {
                "maxTokens": 512,
                "temperature": 0.3,
            },
        }
        if tools:
            kwargs["toolConfig"] = {"tools": tools}
        return kwargs
```

Also update `generate` to accept and pass through `system_prompt`:

```python
    async def generate(
        self,
        user_text: str,
        farmer_profile: dict | None = None,
        conversation_history: list[dict] | None = None,
        tools: list[dict] | None = None,
        tool_executor=None,
        language_code: str = "unknown",
        system_prompt: str | None = None,
    ) -> str:
```

And update all `self._build_kwargs(messages, tools)` calls in `generate` to `self._build_kwargs(messages, tools, system_prompt)`.

**Step 4: Run tests**

```bash
cd /Users/danieleuchar/workspace/gramvaani && PYTHONPATH=src uv run pytest src/tests/test_onboarding_prompt.py -v
```

Expected: All 4 tests PASS.

**Step 5: Run full suite**

```bash
cd /Users/danieleuchar/workspace/gramvaani && PYTHONPATH=src uv run pytest src/tests/ -v
```

Expected: All tests PASS.

**Step 6: Commit**

```bash
git add src/app/pipeline/nova_client.py src/tests/test_onboarding_prompt.py
git commit -m "feat: onboarding system prompt + PROFILE marker extraction"
```

---

### Task 3: Update `process_turn_streaming` to accept and pass `system_prompt`

**Files:**
- Modify: `src/app/pipeline/pipeline.py`

**Context:**
- `process_turn_streaming` calls `nova_client.generate(...)` around line 230
- We need to thread `system_prompt: str | None` through the function signature to Nova
- No new tests needed — the existing pipeline tests still pass; integration tested in Task 5

**Step 1: Update `process_turn_streaming` signature**

Find:
```python
async def process_turn_streaming(
    audio_bytes: bytes,
    farmer_profile: dict | None,
    conversation_history: list[dict],
    language_code: str,
    audio_queue: asyncio.Queue,
    sample_rate: int = 8000,
) -> tuple[str, str, str]:
```

Replace with:
```python
async def process_turn_streaming(
    audio_bytes: bytes,
    farmer_profile: dict | None,
    conversation_history: list[dict],
    language_code: str,
    audio_queue: asyncio.Queue,
    sample_rate: int = 8000,
    system_prompt: str | None = None,
) -> tuple[str, str, str]:
```

**Step 2: Build profile context and pass system_prompt to Nova**

Find the Nova call (around line 230):
```python
    english_response = await nova_client.generate(
        user_text="",
        conversation_history=messages,
        tools=NOVA_TOOLS,
        tool_executor=execute_tool,
    )
```

Replace with:
```python
    # Inject farmer profile as context preamble if available
    effective_prompt = system_prompt
    if effective_prompt is None and farmer_profile:
        name = farmer_profile.get("name", "")
        state = farmer_profile.get("state", "")
        district = farmer_profile.get("district", "")
        profile_ctx = f"Farmer profile — Name: {name}, State: {state}, District: {district}. Default weather and mandi queries to this farmer's state and district unless they specify otherwise."
        from app.pipeline.nova_client import SYSTEM_PROMPT
        effective_prompt = SYSTEM_PROMPT + "\n\n" + profile_ctx

    english_response = await nova_client.generate(
        user_text="",
        conversation_history=messages,
        tools=NOVA_TOOLS,
        tool_executor=execute_tool,
        system_prompt=effective_prompt,
    )
```

**Step 3: Run full test suite**

```bash
cd /Users/danieleuchar/workspace/gramvaani && PYTHONPATH=src uv run pytest src/tests/ -v
```

Expected: All tests PASS.

**Step 4: Commit**

```bash
git add src/app/pipeline/pipeline.py
git commit -m "feat: thread system_prompt + farmer profile context through pipeline"
```

---

### Task 4: Update `GramSaathiHandler` — phone number, DB lookup, onboarding state

**Files:**
- Modify: `src/app/handlers/gram_saathi.py`
- Create: `src/tests/test_gram_saathi_handler.py`

**Context:**
- Handler gets phone via `additional_inputs` from Gradio — passed as the second arg to `_reply_fn`
- FastRTC passes `additional_inputs` as positional args after `audio`
- `copy()` is called for each new connection — it should propagate phone if set
- Onboarding: use `ONBOARDING_PROMPT`; normal: pass `farmer_profile`
- After Nova responds, scan for `<<<PROFILE:>>>` marker using `extract_profile_marker`

**Step 1: Write failing tests**

```python
# src/tests/test_gram_saathi_handler.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.handlers.gram_saathi import GramSaathiHandler


def test_handler_init_defaults():
    h = GramSaathiHandler()
    assert h.phone is None
    assert h.is_onboarding is False
    assert h.farmer_profile is None
    assert h.conversation_history == []


def test_copy_propagates_phone():
    h = GramSaathiHandler()
    h.phone = "+919876543210"
    h2 = h.copy()
    # copy() for a new connection should NOT carry over the phone
    assert h2.phone is None


def test_is_new_user_true_when_name_none():
    from app.models.user import User
    user = User(phone="+919876543210", name=None)
    h = GramSaathiHandler()
    assert h._is_new_user(user) is True


def test_is_new_user_false_when_name_set():
    from app.models.user import User
    user = User(phone="+919876543210", name="Ramesh")
    h = GramSaathiHandler()
    assert h._is_new_user(user) is False
```

**Step 2: Run to confirm failure**

```bash
cd /Users/danieleuchar/workspace/gramvaani && PYTHONPATH=src uv run pytest src/tests/test_gram_saathi_handler.py -v
```

Expected: `AttributeError` — `phone`, `is_onboarding`, `farmer_profile` don't exist yet.

**Step 3: Rewrite `src/app/handlers/gram_saathi.py`**

```python
import asyncio
import io
import logging
import wave
from collections.abc import AsyncGenerator

import numpy as np
from fastrtc import ReplyOnPause

from app.database import get_or_create_user, update_user_profile
from app.models.user import User
from app.pipeline.nova_client import ONBOARDING_PROMPT, extract_profile_marker
from app.pipeline.pipeline import process_turn_streaming

logger = logging.getLogger(__name__)

SAMPLE_RATE = 8000


def _ndarray_to_wav(sample_rate: int, audio: np.ndarray) -> bytes:
    """Convert a numpy int16 array to WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


async def _safe_process_turn_streaming(
    audio_bytes: bytes,
    farmer_profile,
    conversation_history: list[dict],
    language_code: str,
    audio_queue: asyncio.Queue,
    sample_rate: int,
    system_prompt: str | None = None,
) -> tuple[str, str, str]:
    """Wrapper that guarantees None sentinel is put even if pipeline raises."""
    try:
        return await process_turn_streaming(
            audio_bytes=audio_bytes,
            farmer_profile=farmer_profile,
            conversation_history=conversation_history,
            language_code=language_code,
            audio_queue=audio_queue,
            sample_rate=sample_rate,
            system_prompt=system_prompt,
        )
    except Exception:
        logger.exception("process_turn_streaming error")
        await audio_queue.put(None)
        return ("", language_code, "")


class GramSaathiHandler(ReplyOnPause):
    """Voice handler for Gram Saathi.

    ReplyOnPause runs Silero VAD on each incoming audio frame and calls
    _reply_fn only once per complete utterance (after a pause is detected).
    _reply_fn is an async generator that yields (sample_rate, ndarray) audio
    chunks back to the caller as they become available.
    """

    def __init__(self):
        super().__init__(
            fn=self._reply_fn,
            output_sample_rate=SAMPLE_RATE,
            can_interrupt=False,
        )
        self.conversation_history: list[dict] = []
        self.language_code = "hi-IN"
        self.phone: str | None = None
        self.is_onboarding: bool = False
        self.farmer_profile: dict | None = None
        self._profile_loaded: bool = False

    def copy(self) -> "GramSaathiHandler":
        """Called by FastRTC for each new WebRTC/Twilio connection."""
        return GramSaathiHandler()

    def _is_new_user(self, user: User) -> bool:
        return user.name is None

    async def _ensure_profile_loaded(self, phone: str) -> None:
        """Load or create user on first turn. Sets is_onboarding + farmer_profile."""
        if self._profile_loaded:
            return
        self._profile_loaded = True
        self.phone = phone

        user = await get_or_create_user(phone)
        if self._is_new_user(user):
            self.is_onboarding = True
            self.farmer_profile = None
            logger.info("[ONBOARD] New user %s — starting onboarding", phone)
        else:
            self.is_onboarding = False
            self.farmer_profile = {
                "phone": user.phone,
                "name": user.name,
                "state": user.state,
                "district": user.district,
                "language": user.language,
            }
            if user.language:
                self.language_code = user.language
            logger.info("[PROFILE] Returning user %s — %s", phone, user.name)

    async def _reply_fn(self, audio: tuple[int, np.ndarray], phone: str = "") -> AsyncGenerator:
        """Called once per full utterance (after Silero VAD detects a pause).

        phone is passed from the Gradio phone number text box via additional_inputs.
        """
        # Load profile from DB on first turn
        if phone:
            await self._ensure_profile_loaded(phone)

        sample_rate, arr = audio
        wav_bytes = _ndarray_to_wav(sample_rate, arr.reshape(-1))

        system_prompt = ONBOARDING_PROMPT if self.is_onboarding else None

        audio_queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(
            _safe_process_turn_streaming(
                audio_bytes=wav_bytes,
                farmer_profile=self.farmer_profile,
                conversation_history=list(self.conversation_history[-20:]),
                language_code=self.language_code,
                audio_queue=audio_queue,
                sample_rate=SAMPLE_RATE,
                system_prompt=system_prompt,
            )
        )

        # Drain audio queue, yielding each chunk to FastRTC as it arrives
        while True:
            item = await audio_queue.get()
            if item is None:
                break
            yield item

        transcript, detected_lang, english_response = await task

        # Check for PROFILE marker when onboarding
        if self.is_onboarding and english_response:
            profile_data, english_response = extract_profile_marker(english_response)
            if profile_data:
                await update_user_profile(
                    self.phone,
                    name=profile_data.get("name"),
                    state=profile_data.get("state"),
                    district=profile_data.get("district"),
                    language=detected_lang,
                )
                self.farmer_profile = {
                    "phone": self.phone,
                    "name": profile_data.get("name"),
                    "state": profile_data.get("state"),
                    "district": profile_data.get("district"),
                    "language": detected_lang,
                }
                self.is_onboarding = False
                logger.info("[ONBOARD] Profile saved for %s: %s", self.phone, profile_data)

        if transcript:
            self.conversation_history.append(
                {"role": "user", "content": [{"text": transcript}]}
            )
            if english_response:
                self.conversation_history.append(
                    {"role": "assistant", "content": [{"text": english_response}]}
                )
            self.language_code = detected_lang
            logger.info("[%s] user: %s", detected_lang, transcript)
            logger.info("[%s] assistant: %s", detected_lang, english_response)
```

**Step 4: Run tests**

```bash
cd /Users/danieleuchar/workspace/gramvaani && PYTHONPATH=src uv run pytest src/tests/test_gram_saathi_handler.py -v
```

Expected: All 4 tests PASS.

**Step 5: Run full suite**

```bash
cd /Users/danieleuchar/workspace/gramvaani && PYTHONPATH=src uv run pytest src/tests/ -v
```

Expected: All tests PASS.

**Step 6: Commit**

```bash
git add src/app/handlers/gram_saathi.py src/tests/test_gram_saathi_handler.py
git commit -m "feat: handler — phone lookup, onboarding state, PROFILE marker detection"
```

---

### Task 5: Add phone number input to web UI

**Files:**
- Modify: `src/app/main.py`

**Context:**
- FastRTC `Stream` accepts `additional_inputs` — a list of Gradio components
- These are passed as extra positional args to `_reply_fn` after `audio`
- The handler's `_reply_fn(self, audio, phone="")` already expects `phone` as second arg
- We want the record button disabled unless phone is non-empty — use `gr.Textbox` with a JS trigger or set `min_length=1`

**Step 1: Update `src/app/main.py`**

Replace the `stream = Stream(...)` block:

```python
import gradio as gr

phone_input = gr.Textbox(
    label="Phone Number",
    placeholder="+91XXXXXXXXXX",
    max_lines=1,
)

stream = Stream(
    GramSaathiHandler(),
    modality="audio",
    mode="send-receive",
    additional_inputs=[phone_input],
)
stream.mount(app)

# Mount the Gradio UI at /demo for the browser demo
gr.mount_gradio_app(app, stream._ui, path="/demo")
```

Remove the duplicate `import gradio as gr` that was at the bottom (it was inline before). The full updated `main.py`:

```python
from contextlib import asynccontextmanager
import gradio as gr
from fastapi import FastAPI
from fastrtc import Stream

from app.database import init_db
from app.handlers.gram_saathi import GramSaathiHandler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Gram Saathi API", version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "gram-saathi"}


phone_input = gr.Textbox(
    label="Phone Number",
    placeholder="+91XXXXXXXXXX",
    max_lines=1,
)

# FastRTC mounts all voice endpoints:
#   POST /telephone/incoming  — Twilio TwiML webhook
#   WS   /telephone/handler   — Twilio Media Stream WebSocket
#   POST /webrtc/offer        — browser WebRTC signalling
#   GET  /                    — built-in browser demo UI
stream = Stream(
    GramSaathiHandler(),
    modality="audio",
    mode="send-receive",
    additional_inputs=[phone_input],
)
stream.mount(app)

# Mount the Gradio UI at /demo for the browser demo
gr.mount_gradio_app(app, stream._ui, path="/demo")

from app.routers import webhooks, dashboard
app.include_router(webhooks.router)
app.include_router(dashboard.router)
```

**Step 2: Smoke test — server starts cleanly**

```bash
cd /Users/danieleuchar/workspace/gramvaani && PYTHONPATH=src uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 2>&1 | head -10
```

Expected: Server starts, no import errors.

**Step 3: Run full suite**

```bash
cd /Users/danieleuchar/workspace/gramvaani && PYTHONPATH=src uv run pytest src/tests/ -v
```

Expected: All tests PASS.

**Step 4: Commit**

```bash
git add src/app/main.py
git commit -m "feat: add phone number text input to web UI for farmer identification"
```

---

### Task 6: End-to-end manual test + push

**Step 1: Start the server**

```bash
cd /Users/danieleuchar/workspace/gramvaani && PYTHONPATH=src uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Step 2: Open browser demo**

Navigate to `http://localhost:8000/demo`

Verify phone number text box appears above the record button.

**Step 3: New user flow**

1. Enter `+911234567890` in the phone field
2. Click record, speak in Hindi or Tamil
3. Nova should ask for your name in your language
4. Respond with your name, it should ask for state/district
5. Provide state and district
6. Nova should greet you by name and offer to help
7. Ask a mandi/weather question — it should default to your state

**Step 4: Returning user flow**

1. Refresh the page, enter the same phone number again
2. Nova should greet you by name immediately without asking for profile

**Step 5: Push**

```bash
git push origin main
```
