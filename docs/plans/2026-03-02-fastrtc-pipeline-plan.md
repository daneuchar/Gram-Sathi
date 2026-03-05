# FastRTC + Sentence Pipelining + History Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace hand-rolled VAD + WebSocket routers with FastRTC (Silero VAD, browser + Twilio via one handler), add sentence-level parallel translate+TTS, and fix the conversation history bug where assistant responses were never appended.

**Architecture:** A single `GramSaathiHandler(AsyncStreamHandler)` handles both Twilio and browser audio. FastRTC mounts on the FastAPI app, replacing `voice.py` and `demo.py`. Sentence pipelining splits Nova's response into sentences and runs translate+TTS for each sentence in parallel, draining in order into an `asyncio.Queue` that the handler's `emit()` drains.

**Tech Stack:** `fastrtc[vad]` (Silero VAD, AsyncStreamHandler, Stream), `numpy`, existing Sarvam ASR/TTS, Nova Bedrock client.

---

### Task 1: Fix Conversation History

**Files:**
- Modify: `src/app/pipeline/pipeline.py:53`
- Modify: `src/app/routers/voice.py:98-112`
- Modify: `src/app/routers/demo.py:89-111`

**Step 1: Change `process_turn()` return type**

In `pipeline.py`, change the return signature and the two `return` statements:

```python
# Line 53 — change:
) -> tuple[str, str]:
# to:
) -> tuple[str, str, str]:

# Line 66 — change:
    return ("", language_code)
# to:
    return ("", language_code, "")

# Line 80 — change:
    return ("", detected_lang)
# to:
    return ("", detected_lang, "")

# Line 100 — change:
    if not english_response or isinstance(english_response, dict):
        return (english_transcript, detected_lang)
# to:
    if not english_response or isinstance(english_response, dict):
        return (english_transcript, detected_lang, "")

# Line 116 — change:
    return (english_transcript, detected_lang)
# to:
    return (english_transcript, detected_lang, english_response)
```

**Step 2: Update `voice.py` caller**

In `voice.py` `run_turn()`, change:

```python
# Change (lines 101-112):
            transcript, detected_lang = await process_turn(
                wav_bytes,
                farmer_profile=None,
                conversation_history=list(conversation_history),
                language_code=language_code,
                audio_send_callback=audio_send_callback,
            )
            if transcript:
                conversation_history.append(
                    {"role": "user", "content": [{"text": transcript}]}
                )
                language_code = detected_lang
                logger.info("[%s] %s", detected_lang, transcript)
# To:
            transcript, detected_lang, assistant_response = await process_turn(
                wav_bytes,
                farmer_profile=None,
                conversation_history=list(conversation_history),
                language_code=language_code,
                audio_send_callback=audio_send_callback,
            )
            if transcript:
                conversation_history.append(
                    {"role": "user", "content": [{"text": transcript}]}
                )
                if assistant_response:
                    conversation_history.append(
                        {"role": "assistant", "content": [{"text": assistant_response}]}
                    )
                language_code = detected_lang
                logger.info("[%s] %s", detected_lang, transcript)
```

**Step 3: Update `demo.py` caller**

Same change in `demo.py` `run_turn()` — unpack 3-tuple and append both user and assistant turns.

```python
# Change (lines 92-105):
            transcript, detected_lang = await process_turn(
                wav_bytes,
                farmer_profile=None,
                conversation_history=list(conversation_history),
                language_code=language_code,
                audio_send_callback=send_audio,
            )
            if transcript:
                conversation_history.append(
                    {"role": "user", "content": [{"text": transcript}]}
                )
                language_code = detected_lang
                await websocket.send_json({"event": "transcript", "text": transcript})
                logger.info("[%s] %s", detected_lang, transcript)
# To:
            transcript, detected_lang, assistant_response = await process_turn(
                wav_bytes,
                farmer_profile=None,
                conversation_history=list(conversation_history),
                language_code=language_code,
                audio_send_callback=send_audio,
            )
            if transcript:
                conversation_history.append(
                    {"role": "user", "content": [{"text": transcript}]}
                )
                if assistant_response:
                    conversation_history.append(
                        {"role": "assistant", "content": [{"text": assistant_response}]}
                    )
                language_code = detected_lang
                await websocket.send_json({"event": "transcript", "text": transcript})
                logger.info("[%s] %s", detected_lang, transcript)
```

**Step 4: Start the server and do a quick smoke test**

```bash
cd /Users/danieleuchar/workspace/gramvaani
uv run uvicorn app.main:app --reload --port 8000
```

Open the browser demo, ask two follow-up questions, verify the second answer references context from the first. Stop the server.

**Step 5: Commit**

```bash
git add src/app/pipeline/pipeline.py src/app/routers/voice.py src/app/routers/demo.py
git commit -m "fix: append assistant turn to conversation history after each response"
```

---

### Task 2: Sentence-Level Pipelining in pipeline.py

**Files:**
- Modify: `src/app/pipeline/pipeline.py`

**Background:** Currently `process_turn()` calls `synthesize_streaming()` sequentially — full TTS of the whole response before any audio plays back. The new `process_turn_streaming()` splits the English response into sentences and runs translate+TTS for all sentences in parallel, then drains them in order into a caller-supplied `asyncio.Queue[tuple[int, np.ndarray] | None]`. A `None` sentinel signals end of turn.

The old `process_turn()` (with callback) stays for backward compat until Task 4 deletes `voice.py` and `demo.py`.

**Step 1: Add numpy import and helpers at top of pipeline.py**

Add to the imports section at the top of `pipeline.py`:

```python
import numpy as np
```

After `_expand_numbers()`, add these two helpers:

```python
_SENTENCE_RE = re.compile(r'(?<=[.!?।])\s+')


def _split_sentences(text: str) -> list[str]:
    """Split English response into sentences on . ! ? ।"""
    parts = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
    return parts if parts else [text]


async def _translate_and_tts(
    sentence: str,
    detected_lang: str,
    is_english: bool,
    q: asyncio.Queue,
    sample_rate: int = 8000,
) -> None:
    """Translate one sentence and synthesize it; put (sr, ndarray) chunks into q, then None."""
    try:
        text = sentence if is_english else await from_english(sentence, detected_lang)
        async for chunk in synthesize_streaming(text, detected_lang, sample_rate=sample_rate):
            arr = np.frombuffer(chunk, dtype=np.int16).copy()
            await q.put((sample_rate, arr))
    except Exception:
        logger.exception("_translate_and_tts error for: %r", sentence)
    finally:
        await q.put(None)  # per-sentence sentinel
```

**Step 2: Add `process_turn_streaming()` below `process_turn()`**

```python
async def process_turn_streaming(
    audio_bytes: bytes,
    farmer_profile: dict | None,
    conversation_history: list[dict],
    language_code: str,
    audio_queue: asyncio.Queue,
    sample_rate: int = 8000,
) -> tuple[str, str, str]:
    """Process one voice turn with sentence-level parallel TTS pipelining.

    Puts (sample_rate, np.ndarray) tuples into audio_queue as audio becomes ready.
    Puts a final None sentinel when the turn is fully done.
    Returns (english_transcript, detected_lang, english_response).
    """
    if not audio_bytes:
        await audio_queue.put(None)
        return ("", language_code, "")

    is_english = language_code in ENGLISH_LANGS

    # 1. ASR
    asr_result = await transcribe(
        audio_bytes,
        language_code,
        mode="transcribe" if is_english else "translate",
    )
    transcript = asr_result["transcript"]
    detected_lang = asr_result["language_code"]

    if not transcript.strip():
        await audio_queue.put(None)
        return ("", detected_lang, "")

    is_english = detected_lang in ENGLISH_LANGS

    # 2. Filler — pre-generated, 0ms
    filler = get_filler_audio(detected_lang, sample_rate=sample_rate)
    if filler:
        arr = np.frombuffer(filler, dtype=np.int16).copy()
        await audio_queue.put((sample_rate, arr))

    # 3. Nova — non-streaming, handles tool calls correctly
    messages = list(conversation_history)
    messages.append({"role": "user", "content": [{"text": transcript}]})
    english_response = await nova_client.generate(
        user_text="",
        conversation_history=messages,
        tools=NOVA_TOOLS,
        tool_executor=execute_tool,
    )

    if not english_response or isinstance(english_response, dict):
        await audio_queue.put(None)
        return (transcript, detected_lang, "")

    english_response = _expand_numbers(english_response)

    # 4. Sentence-level parallel translate + TTS
    sentences = _split_sentences(english_response)

    # Each sentence gets its own queue so we can start all in parallel but drain in order
    sent_queues: list[asyncio.Queue] = [asyncio.Queue() for _ in sentences]
    tasks = [
        asyncio.create_task(
            _translate_and_tts(sent, detected_lang, is_english, sent_queues[i], sample_rate)
        )
        for i, sent in enumerate(sentences)
    ]

    # Drain sentence queues in order — sentence N+1 may already be ready while N plays
    for q in sent_queues:
        while True:
            item = await q.get()
            if item is None:
                break
            await audio_queue.put(item)

    await asyncio.gather(*tasks)  # ensure all tasks cleaned up
    await audio_queue.put(None)   # turn-level sentinel
    return (transcript, detected_lang, english_response)
```

**Step 3: Quick unit test (manual)**

Open a Python REPL in the project directory:

```bash
uv run python -c "
import asyncio, sys
sys.path.insert(0, 'src')
from app.pipeline.pipeline import _split_sentences
print(_split_sentences('Hello world. How are you? I am fine!'))
print(_split_sentences('टमाटर का भाव बारह सौ रुपए प्रति क्विंटल है।'))
print(_split_sentences('Single sentence without punctuation'))
"
```

Expected output:
```
['Hello world.', 'How are you?', 'I am fine!']
['टमाटर का भाव बारह सौ रुपए प्रति क्विंटल है।']
['Single sentence without punctuation']
```

**Step 4: Commit**

```bash
git add src/app/pipeline/pipeline.py
git commit -m "feat: sentence-level parallel translate+TTS via process_turn_streaming()"
```

---

### Task 3: Install FastRTC and Create GramSaathiHandler

**Files:**
- Modify: `pyproject.toml`
- Create: `src/app/handlers/__init__.py`
- Create: `src/app/handlers/gram_saathi.py`

**Background:** FastRTC's `AsyncStreamHandler.receive()` is called once per utterance (after Silero VAD detects end-of-speech) with `(sample_rate, np.ndarray)`. `emit()` is called continuously — return `(sample_rate, np.ndarray)` to send audio, or `None` if nothing to send. `Stream(GramSaathiHandler, ...)` creates a FastAPI-mountable object that registers `/telephone/incoming` (Twilio TwiML), `/telephone/handler` (Twilio Media Stream WS), `/webrtc/offer` (browser WebRTC signalling), and `/` (built-in browser UI).

**Step 1: Install fastrtc**

```bash
cd /Users/danieleuchar/workspace/gramvaani
uv add "fastrtc[vad]" numpy
```

Verify it added to `pyproject.toml` under `dependencies`.

> Note: `fastrtc[vad]` pulls in PyTorch (for Silero VAD). First install may take a few minutes.

**Step 2: Create `src/app/handlers/__init__.py`**

```python
```

(empty file — just marks it as a package)

**Step 3: Create `src/app/handlers/gram_saathi.py`**

```python
import asyncio
import io
import logging
import wave

import numpy as np
from fastrtc import AsyncStreamHandler

from app.pipeline.pipeline import process_turn_streaming
from app.pipeline.sarvam_asr import ENGLISH_LANGS

logger = logging.getLogger(__name__)

SAMPLE_RATE = 8000
FRAME_SIZE = 960  # ~120ms at 8kHz


def _ndarray_to_wav(sample_rate: int, audio: np.ndarray) -> bytes:
    """Convert a numpy int16 array to WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


class GramSaathiHandler(AsyncStreamHandler):
    """Single handler for both Twilio phone calls and browser WebRTC sessions.

    FastRTC handles:
    - Silero VAD: detects speech start/end, passes full utterance to receive()
    - Sample-rate conversion: Twilio 8kHz mulaw ↔ handler's working rate
    - can_interrupt=False: sequential turn-taking, no echo feedback
    """

    def __init__(self):
        super().__init__(
            output_sample_rate=SAMPLE_RATE,
            output_frame_size=FRAME_SIZE,
        )
        self.conversation_history: list[dict] = []
        self.language_code = "hi-IN"
        self.audio_queue: asyncio.Queue = asyncio.Queue()

    async def receive(self, frame: tuple[int, np.ndarray]) -> None:
        """Called by FastRTC when a full utterance is ready (after VAD silence)."""
        sample_rate, audio = frame
        wav_bytes = _ndarray_to_wav(sample_rate, audio)
        asyncio.create_task(self._run_turn(wav_bytes))

    async def emit(self) -> tuple[int, np.ndarray] | None:
        """Called continuously by FastRTC — return next audio chunk or None."""
        try:
            item = await asyncio.wait_for(self.audio_queue.get(), timeout=0.02)
            # None is the turn-done sentinel; return None to FastRTC (no audio)
            return item  # either (sr, array) or None
        except asyncio.TimeoutError:
            return None

    async def _run_turn(self, wav_bytes: bytes) -> None:
        try:
            transcript, detected_lang, assistant_response = await process_turn_streaming(
                audio_bytes=wav_bytes,
                farmer_profile=None,
                conversation_history=list(self.conversation_history),
                language_code=self.language_code,
                audio_queue=self.audio_queue,
                sample_rate=SAMPLE_RATE,
            )
            if transcript:
                self.conversation_history.append(
                    {"role": "user", "content": [{"text": transcript}]}
                )
                if assistant_response:
                    self.conversation_history.append(
                        {"role": "assistant", "content": [{"text": assistant_response}]}
                    )
                self.language_code = detected_lang
                logger.info("[%s] user: %s", detected_lang, transcript)
                logger.info("[%s] assistant: %s", detected_lang, assistant_response)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("GramSaathiHandler._run_turn error")
            await self.audio_queue.put(None)  # ensure sentinel even on error
```

**Step 4: Verify FastRTC import**

```bash
uv run python -c "from fastrtc import AsyncStreamHandler, Stream; print('FastRTC OK')"
```

Expected: `FastRTC OK`

**Step 5: Commit**

```bash
git add pyproject.toml src/app/handlers/
git commit -m "feat: GramSaathiHandler — FastRTC AsyncStreamHandler for Twilio + browser"
```

---

### Task 4: Wire FastRTC into main.py and Update Twilio Webhook URL

**Files:**
- Modify: `src/app/main.py`
- Modify: `src/app/routers/webhooks.py:43`

**Step 1: Update `main.py`**

Replace the entire content of `src/app/main.py` with:

```python
from contextlib import asynccontextmanager
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


# FastRTC: one Stream mounts all voice endpoints:
#   POST /telephone/incoming  — Twilio TwiML webhook
#   WS   /telephone/handler   — Twilio Media Stream WebSocket
#   POST /webrtc/offer        — browser WebRTC signalling
#   GET  /                    — built-in browser demo UI
stream = Stream(
    GramSaathiHandler,
    modality="audio",
    mode="send-receive",
)
stream.mount(app)

from app.routers import webhooks, dashboard
app.include_router(webhooks.router)
app.include_router(dashboard.router)
```

**Step 2: Update Twilio TwiML URL in webhooks.py**

In `src/app/routers/webhooks.py`, change line 43:

```python
# Change:
    ws_url = f"{settings.public_url.replace('https://', 'wss://')}/ws/voice"
# To:
    ws_url = f"{settings.public_url.replace('https://', 'wss://')}/telephone/handler"
```

**Step 3: Start the server**

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Verify no import errors. Then open `http://localhost:8000/` — you should see the FastRTC built-in browser demo UI (not the old `index.html`).

**Step 4: Test browser audio (FastRTC built-in UI)**

In the FastRTC UI, click to start a session and speak a Hindi question. Verify:
- Filler audio plays immediately
- Bot responds in Hindi
- A follow-up question shows the bot has context (history fix working)
- Sentence 1 audio starts playing before sentence 2 is synthesized (pipelining working)

**Step 5: Test Twilio (if ngrok is running)**

```bash
# In another terminal:
ngrok http 8000
```

Update the Twilio console webhook URL to: `https://<ngrok-id>.ngrok.io/webhooks/inbound-call`

Call the Twilio number and verify phone call works end-to-end.

**Step 6: Delete the old routers**

```bash
rm src/app/routers/voice.py
rm src/app/routers/demo.py
rm src/app/static/index.html  # replaced by FastRTC built-in UI
```

**Step 7: Commit**

```bash
git add src/app/main.py src/app/routers/webhooks.py
git rm src/app/routers/voice.py src/app/routers/demo.py src/app/static/index.html
git commit -m "feat: mount FastRTC Stream — replaces hand-rolled VAD WebSocket routers"
```

---

## Quick Reference

| Old endpoint | New endpoint | Notes |
|---|---|---|
| `POST /webhooks/inbound-call` | `POST /webhooks/inbound-call` | Unchanged — just update TwiML URL inside |
| `WS /ws/voice` | `WS /telephone/handler` | FastRTC Twilio Media Stream |
| `WS /ws/demo` | `POST /webrtc/offer` | FastRTC WebRTC signalling |
| `GET /` | `GET /` | FastRTC built-in UI |

## Files Deleted

- `src/app/routers/voice.py` — replaced by `src/app/handlers/gram_saathi.py`
- `src/app/routers/demo.py` — replaced by `src/app/handlers/gram_saathi.py`
- `src/app/static/index.html` — replaced by FastRTC built-in browser UI

## Files Created

- `src/app/handlers/__init__.py`
- `src/app/handlers/gram_saathi.py`

## Files Modified

- `src/app/pipeline/pipeline.py` — history fix + `process_turn_streaming()` + helpers
- `src/app/main.py` — mount FastRTC Stream, remove old routers
- `src/app/routers/webhooks.py` — update TwiML WebSocket URL
- `pyproject.toml` — add `fastrtc[vad]`
