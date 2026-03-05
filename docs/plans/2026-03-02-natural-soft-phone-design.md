# Natural Soft Phone — Design

## Goal
Replace the hold-to-talk demo UI with a phone-call-like experience: click to call, speak naturally, bot listens via VAD and responds only after the user finishes.

## Approach: Frontend VAD

Browser detects speech/silence locally (zero latency) using Web Audio `AnalyserNode`. Backend stays simple — processes one utterance at a time.

## Protocol (WebSocket events)

| Direction | Event | Payload | Meaning |
|---|---|---|---|
| Client → Server | `start` | `{sample_rate, language_code}` | Call begins |
| Client → Server | `media` | `{payload: base64_pcm}` | Audio chunk for current utterance |
| Client → Server | `query` | — | VAD detected end of speech — process it |
| Client → Server | `interrupt` | — | User spoke during bot playback — cancel + process |
| Client → Server | `end_call` | — | User hung up |
| Server → Client | `media` | `{payload: base64_pcm}` | TTS audio chunk |
| Server → Client | `transcript` | `{text}` | User utterance text |
| Server → Client | `done` | — | Bot finished responding, ready for next turn |

## Frontend VAD Parameters

- `SPEECH_THRESHOLD = 0.015` RMS (float 0–1) — above = speech
- `SILENCE_MS = 1200` — ms of quiet after speech ends the turn
- `MIN_SPEECH_MS = 400` — ignore blips shorter than this
- `BARGE_IN_THRESHOLD = 0.02` — speech energy during bot playback triggers interrupt

## UI States

```
[idle] → click call → [connecting] → ws open → [listening]
[listening] → VAD speech start → waveform active
[listening] → VAD silence after speech → [processing] → send query
[processing] → server sends media → [bot speaking]
[bot speaking] → VAD detects user speech → send interrupt → [listening]
[bot speaking] → server sends done → [listening]
[any] → click end call → [idle]
```

## UI Layout

- Phone-like dark screen, centered
- Farmer avatar + "Gram Saathi" contact name
- Live call timer (mm:ss)
- Status label (Listening / Processing / Bot speaking)
- Animated waveform bars (visible when user is speaking)
- Transcript bubbles scrolling below
- Single red end-call button at bottom

## Files Changed

- `src/app/routers/demo.py` — handle `query`, `interrupt`, `end_call` events; use `asyncio.create_task` for non-blocking TTS
- `src/app/static/index.html` — full redesign with phone UI + frontend VAD
