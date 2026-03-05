# FastRTC + Sentence Pipelining + History Fix — Design

## Goals

1. Replace hand-rolled VAD + WebSocket handlers with FastRTC (Silero VAD, proper barge-in, Twilio and browser WebRTC handled by the framework)
2. Sentence-level TTS pipelining — translate + synthesize sentence N+1 while sentence N is playing
3. Fix conversation history — assistant responses currently never appended, breaking multi-turn context

---

## 1. FastRTC Integration

### Architecture

```
app.py
  stream = Stream(GramSaathiHandler, modality="audio", mode="send-receive")
  stream.mount(app)
    → POST /telephone/incoming   (Twilio TwiML webhook — replaces /webhooks/inbound-call)
    → WS   /telephone/handler    (Twilio Media Stream WebSocket — replaces /ws/voice)
    → POST /webrtc/offer         (browser WebRTC signalling — replaces /ws/demo)
    → GET  /                     (FastRTC browser UI — replaces index.html demo page)
```

### GramSaathiHandler

Single `AsyncStreamHandler` subclass used for both Twilio and browser. FastRTC handles:
- Silero VAD (detects speech start/end, no RMS threshold tuning needed)
- Sample rate conversion (Twilio 8kHz mulaw ↔ handler's working rate)
- `can_interrupt=False` — sequential turn-taking (no echo feedback)

```python
class GramSaathiHandler(AsyncStreamHandler):
    def __init__(self):
        super().__init__(output_sample_rate=8000, output_frame_size=960)
        self.conversation_history = []
        self.language_code = "hi-IN"
        self.audio_queue = asyncio.Queue()

    async def receive(self, frame: tuple[int, np.ndarray]) -> None:
        # frame = (sample_rate, int16 numpy array) — full utterance after VAD pause
        wav_bytes = ndarray_to_wav(frame)
        asyncio.create_task(self._process_turn(wav_bytes))

    async def emit(self) -> tuple[int, np.ndarray] | None:
        # Drain audio_queue — yields chunks as sentence pipeline produces them
        return await self.audio_queue.get()

    async def _process_turn(self, wav_bytes):
        # Calls updated process_turn() which streams sentence audio into audio_queue
        ...
```

### Files changed

| File | Change |
|---|---|
| `src/app/routers/voice.py` | Replaced by `src/app/handlers/gram_saathi.py` |
| `src/app/routers/demo.py` | Replaced by `src/app/handlers/gram_saathi.py` |
| `src/app/static/index.html` | Replaced by FastRTC's built-in browser UI |
| `src/app/main.py` | Mount `Stream(GramSaathiHandler)` instead of voice/demo routers |
| `src/app/routers/webhooks.py` | `/webhooks/inbound-call` kept for backward compat; Twilio console updated to `/telephone/incoming` |

### Installation

```bash
uv add "fastrtc[vad]"
uv add numpy
```

---

## 2. Sentence-Level TTS Pipelining

### Current flow (slow)

```
Nova.generate() [waits for full response]
  → translate(full_text)          [waits]
  → synthesize_streaming(full)    [streams chunks]
```

### New flow (fast)

```
Nova.generate_stream() [streams tokens]
  → sentence_accumulator (splits on . ! ?)
      sentence 1 done → asyncio.create_task(translate → TTS) → enqueue chunks
      sentence 2 done → asyncio.create_task(translate → TTS) → enqueue chunks
      ...
  → audio_queue drains in order, yielding chunks as they arrive
```

### Implementation in `pipeline.py`

```python
async def process_turn_streaming(wav_bytes, ..., audio_queue: asyncio.Queue):
    # 1. ASR
    transcript, lang = await transcribe(...)

    # 2. Filler
    filler = get_filler_audio(lang, 8000)
    if filler: await audio_queue.put(bytes_to_ndarray(filler))

    # 3. Stream Nova tokens → accumulate sentences
    sentence_buf = ""
    sentence_tasks = []
    async for token in nova_client.generate_stream(messages):
        sentence_buf += token
        if sentence_buf.endswith(('.', '!', '?', '।')):   # ।  = Devanagari full stop
            sentence_tasks.append(asyncio.create_task(
                _translate_and_tts(sentence_buf.strip(), lang, audio_queue)
            ))
            sentence_buf = ""

    # Flush remaining
    if sentence_buf.strip():
        sentence_tasks.append(asyncio.create_task(
            _translate_and_tts(sentence_buf.strip(), lang, audio_queue)
        ))

    await asyncio.gather(*sentence_tasks)
    await audio_queue.put(None)  # sentinel — done
```

---

## 3. Conversation History Fix

### Problem

`process_turn()` returns `(transcript, lang)`. The Nova English response is generated internally but discarded. `voice.py`/`demo.py` append only the user turn:

```python
conversation_history.append({"role": "user", "content": [{"text": transcript}]})
# assistant response NEVER added → Nova starts fresh every turn
```

### Fix

Return `english_response` from `process_turn()` (new third return value):

```python
return (english_transcript, detected_lang, english_response)
```

Callers append both turns:

```python
transcript, lang, assistant_response = await process_turn(...)
if transcript:
    conversation_history.append({"role": "user",      "content": [{"text": transcript}]})
    conversation_history.append({"role": "assistant", "content": [{"text": assistant_response}]})
```

---

## Implementation Order

1. Fix conversation history (smallest, independent)
2. Sentence pipelining (depends on nova_client.generate_stream)
3. FastRTC handler (depends on updated pipeline)
4. Wire into main.py + update Twilio console webhook URL

---

## Keep Unchanged

- `sarvam_asr.py` — saaras:v3 ASR
- `sarvam_tts.py` — bulbul:v2 streaming TTS
- `sarvam_translate.py` — from_english translation
- `nova_client.py` — `generate_stream()` already exists, no changes needed
- `tools/` — all tool implementations unchanged
- `webhooks.py` — call-status endpoint unchanged
