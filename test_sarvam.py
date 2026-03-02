"""
Full voice pipeline test — Mic → ASR → Nova Lite → TTS → Speaker
Measures latency at every step and plays response audio back.

Usage:
    PYTHONPATH=src uv run python test_sarvam.py

Controls:
    Press ENTER to start recording
    Press ENTER again to stop
    Type 'q' + ENTER to quit
"""
import asyncio
import base64
import io
import json
import os
import re
import time
import threading
import wave
from dotenv import load_dotenv

load_dotenv()

import boto3
import httpx
import numpy as np
import sounddevice as sd
import websockets

# ── Config ────────────────────────────────────────────────────────────────────
SARVAM_API_KEY  = os.environ["SARVAM_API_KEY"]
AWS_KEY         = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET      = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION      = os.environ.get("AWS_DEFAULT_REGION", "ap-south-1")
BEDROCK_MODEL   = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

SARVAM_HEADERS  = {"api-subscription-key": SARVAM_API_KEY}
RECORD_SR       = 16000   # mic sample rate
TTS_SR          = 22050   # bulbul:v3 — 22050Hz for natural local playback (8000 for phone calls)

FILLER_TEXT = {
    "hi-IN": "हाँ जी, एक पल।",
    "ta-IN": "சரி, ஒரு நிமிடம்.",
    "en-IN": "One moment.",
    "en-US": "One moment.",
    "default": "One moment.",
}

# Pre-synthesized filler audio — cached at startup so filler plays instantly (0ms wait)
FILLER_CACHE: dict[str, bytes] = {}

SYSTEM_PROMPT = (
    "You are Gram Saathi, a voice assistant for Indian farmers. "
    "Always respond in English — responses will be translated to the farmer's language automatically. "
    "Keep replies under 3 short sentences — this is a phone call, be concise. "
    "Never fabricate prices or data — say so clearly if you don't have it."
)
ENGLISH_LANGS = {"en-IN", "en-US", "en-GB", "en"}

has_aws = bool(AWS_KEY and AWS_SECRET)

# ── Bedrock client ────────────────────────────────────────────────────────────
bedrock = None
if has_aws:
    bedrock = boto3.client(
        "bedrock-runtime",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_KEY,
        aws_secret_access_key=AWS_SECRET,
    )

# ── Audio helpers ─────────────────────────────────────────────────────────────

def record_until_enter() -> np.ndarray:
    frames = []
    active = threading.Event()
    active.set()

    def callback(indata, *_):
        if active.is_set():
            frames.append(indata.copy())

    with sd.InputStream(samplerate=RECORD_SR, channels=1, dtype="float32", callback=callback):
        input()
        active.clear()

    return np.concatenate(frames) if frames else np.array([])


def to_wav(audio_np: np.ndarray, sr: int = RECORD_SR) -> bytes:
    pcm = (np.clip(audio_np.flatten(), -1, 1) * 32767).astype(np.int16).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes(pcm)
    return buf.getvalue()


def play_audio(pcm_bytes: bytes, sr: int = TTS_SR):
    """Play raw PCM int16 bytes through speakers."""
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32767
    sd.play(audio, samplerate=sr, blocking=True)


def warmup_fillers():
    """Pre-synthesize all filler phrases once at startup and cache them.
    Eliminates TTS latency for fillers — they play instantly on demand.
    """
    print("⏳ Pre-synthesizing filler phrases...", end=" ", flush=True)
    t0 = time.perf_counter()
    for lang, text in FILLER_TEXT.items():
        if lang == "default":
            continue
        try:
            audio, _ = run_tts(text, lang if lang != "default" else "en-IN")
            FILLER_CACHE[lang] = audio
        except Exception:
            pass
    # fallback
    if "en-IN" in FILLER_CACHE:
        FILLER_CACHE["default"] = FILLER_CACHE["en-IN"]
    ms = (time.perf_counter() - t0) * 1000
    print(f"done ({ms:.0f}ms) — fillers cached for {list(FILLER_CACHE.keys())}")


def split_sentences(text: str) -> list[str]:
    """Split on sentence-ending punctuation."""
    parts = re.split(r"(?<=[।.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


async def _stream_tts_play(text: str, lang: str) -> float:
    """WebSocket streaming TTS — play chunks as they arrive.
    First audio starts in ~400ms. Returns total ms."""
    speaker = {
        "hi-IN": "kavya", "ta-IN": "kavitha", "te-IN": "gokul",
        "en-IN": "anand", "en-US": "anand",
    }.get(lang, "kavya")

    uri = "wss://api.sarvam.ai/text-to-speech/ws?model=bulbul:v3-beta&send_completion_event=true"
    headers = {"Api-Subscription-Key": SARVAM_API_KEY}
    t0 = time.perf_counter()
    ttfa = None

    async with websockets.connect(uri, additional_headers=headers) as ws:
        await ws.send(json.dumps({"type": "config", "data": {
            "target_language_code": lang, "speaker": speaker,
            "pace": 1.0, "speech_sample_rate": str(TTS_SR),
            "model": "bulbul:v3-beta", "output_audio_codec": "linear16",
        }}))
        await ws.send(json.dumps({"type": "text", "data": {"text": text}}))
        await ws.send(json.dumps({"type": "flush"}))

        try:
            async for message in ws:
                msg = json.loads(message)
                if msg["type"] == "audio":
                    if ttfa is None:
                        ttfa = (time.perf_counter() - t0) * 1000
                    pcm = base64.b64decode(msg["data"]["audio"])
                    play_audio(pcm)
                elif msg["type"] == "event":
                    break
                elif msg["type"] == "error":
                    break
        except websockets.exceptions.ConnectionClosed:
            pass

    return (time.perf_counter() - t0) * 1000, ttfa or 0


def run_tts_streaming(text: str, lang: str) -> tuple[float, float]:
    """Sync wrapper for WebSocket streaming TTS. Returns (total_ms, ttfa_ms)."""
    return asyncio.run(_stream_tts_play(text, lang))


def play_tts_with_overlap(text: str, lang: str) -> float:
    """Sentence-split TTS with overlap: play sentence N while synthesizing sentence N+1.

    Returns total TTS time (ms).
    """
    sentences = split_sentences(text)
    if not sentences:
        return 0.0

    t0 = time.perf_counter()

    if len(sentences) == 1:
        audio, ms = run_tts(sentences[0], lang)
        play_audio(audio)
        return (time.perf_counter() - t0) * 1000

    # Synthesize first sentence immediately
    next_audio_holder = [None]
    next_audio_holder[0], _ = run_tts(sentences[0], lang)

    for i, sentence in enumerate(sentences):
        current_audio = next_audio_holder[0]

        # Kick off synthesis of NEXT sentence in background thread
        if i + 1 < len(sentences):
            next_audio_holder[0] = None
            def _synth_next(s=sentences[i + 1]):
                next_audio_holder[0], _ = run_tts(s, lang)
            t = threading.Thread(target=_synth_next, daemon=True)
            t.start()

        # Play current sentence (blocks until done — next sentence synthesizes in parallel)
        play_audio(current_audio)

        # If next sentence isn't ready yet, wait briefly
        if i + 1 < len(sentences):
            t.join()

    return (time.perf_counter() - t0) * 1000


# ── Pipeline steps ────────────────────────────────────────────────────────────

def run_asr(wav_bytes: bytes, mode: str = "translate") -> tuple[str, str, float]:
    """ASR with saaras:v3.

    mode='translate'  → returns English directly (ASR + translate in one call)
    mode='transcribe' → returns transcript in detected language

    Returns (transcript, detected_language_code, latency_ms).
    """
    t0 = time.perf_counter()
    resp = httpx.post(
        "https://api.sarvam.ai/speech-to-text",
        headers=SARVAM_HEADERS,
        data={"model": "saaras:v3", "language_code": "unknown",
              "with_timestamps": "false", "mode": mode},
        files={"file": ("audio.wav", io.BytesIO(wav_bytes), "audio/wav")},
        timeout=30,
    )
    resp.raise_for_status()
    ms = (time.perf_counter() - t0) * 1000
    d = resp.json()
    return d.get("transcript", ""), d.get("language_code", "unknown"), ms


def run_tts(text: str, lang: str) -> tuple[bytes, float]:
    """Returns (pcm_bytes, latency_ms). Uses bulbul:v3 for natural Indian voices."""
    # bulbul:v3 language-specific speakers
    speaker = {
        "hi-IN": "kavya",      # Hindi female — warm, natural
        "ta-IN": "kavitha",    # Tamil female — native Tamil speaker
        "te-IN": "gokul",      # Telugu male — native Telugu speaker
        "mr-IN": "roopa",      # Marathi female
        "kn-IN": "shruti",     # Kannada female
        "bn-IN": "kabir",      # Bengali male
        "en-IN": "anand",      # English Indian accent
        "en-US": "anand",
    }.get(lang, "kavya")
    t0 = time.perf_counter()
    resp = httpx.post(
        "https://api.sarvam.ai/text-to-speech",
        headers=SARVAM_HEADERS,
        json={
            "inputs": [text],
            "target_language_code": lang,
            "speaker": speaker,
            "pace": 1.0,               # natural pace
            "speech_sample_rate": TTS_SR,
            "model": "bulbul:v3",
            "temperature": 0.8,        # higher = more expressive, less robotic
        },
        timeout=30,
    )
    resp.raise_for_status()
    ms = (time.perf_counter() - t0) * 1000
    import base64
    return base64.b64decode(resp.json()["audios"][0]), ms


def sarvam_translate(text: str, src: str, tgt: str) -> str:
    """Translate text using Sarvam sarvam-translate:v1."""
    if src == tgt or (src in ENGLISH_LANGS and tgt in ENGLISH_LANGS):
        return text
    resp = httpx.post("https://api.sarvam.ai/translate",
        headers={**SARVAM_HEADERS, "Content-Type": "application/json"},
        json={"input": text, "source_language_code": src,
              "target_language_code": tgt, "model": "sarvam-translate:v1"},
        timeout=15)
    resp.raise_for_status()
    return resp.json().get("translated_text", text)


def run_nova(english_transcript: str, history: list) -> tuple[str, float, float]:
    """Send English transcript to Nova, get English response.
    Returns (english_response, ttft_ms, total_ms).
    """
    if not has_aws:
        return "[AWS keys not set — add to .env to enable Nova]", 0, 0

    messages = list(history)
    messages.append({"role": "user", "content": [{"text": english_transcript}]})

    t0 = time.perf_counter()
    ttft = None
    full_text = ""

    response = bedrock.converse_stream(
        modelId=BEDROCK_MODEL,
        system=[{"text": SYSTEM_PROMPT}],
        messages=messages,
        inferenceConfig={"maxTokens": 256, "temperature": 0.7},
    )

    for event in response["stream"]:
        if "contentBlockDelta" in event:
            delta = event["contentBlockDelta"]["delta"]
            if "text" in delta:
                if ttft is None:
                    ttft = (time.perf_counter() - t0) * 1000
                full_text += delta["text"]
                print(delta["text"], end="", flush=True)

    total_ms = (time.perf_counter() - t0) * 1000
    print()
    return full_text.strip(), ttft or 0, total_ms


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("  Gram Saathi — Full Pipeline Test")
    print("  Mic → ASR → Nova Lite → TTS → Speaker")
    print("=" * 62)
    if not has_aws:
        print("  ⚠️  AWS keys not set — Nova step will be skipped")
        print("     Add AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY to .env")
    print("  Type 'q' + ENTER to quit\n")

    # Warm up filler cache — synthesize once, play instantly on every turn
    warmup_fillers()
    print()

    history = []
    session = 0

    while True:
        session += 1
        print(f"─── Turn {session} " + "─" * 44)
        print("Press ENTER to speak... (or 'q' + ENTER to quit)")

        cmd = input()
        if cmd.strip().lower() == "q":
            print("Bye!")
            break

        # ── 1. Record ─────────────────────────────────────────────────────────
        print("🔴 Recording... press ENTER to stop")
        t_start = time.perf_counter()
        audio = record_until_enter()
        rec_dur = time.perf_counter() - t_start

        if audio.size == 0 or rec_dur < 0.3:
            print("⚠️  Too short, try again\n"); continue

        wav = to_wav(audio)
        print(f"⏹  {rec_dur:.1f}s recorded\n")

        t_turn_start = time.perf_counter()

        # ── 2. ASR + translate in ONE call (mode=translate → English directly) ──
        print("⏳ ASR + translate...", end=" ", flush=True)
        is_english_guess = False  # will recheck after detection
        english_transcript, lang, asr_ms = run_asr(wav, mode="translate")
        is_english = lang in ENGLISH_LANGS
        # If English detected, re-run as transcribe (mode=translate on English returns same text anyway)
        print(f"done ({asr_ms:.0f}ms)")
        print(f"📝 [{lang}] EN: {english_transcript!r}\n")

        if not english_transcript.strip():
            print("⚠️  Empty transcript, try again\n"); continue

        tr_in_ms = 0  # no separate translate step needed

        # ── 4. Filler — play from cache instantly (0ms wait) ─────────────────
        filler_audio = FILLER_CACHE.get(lang) or FILLER_CACHE.get("default")
        if filler_audio:
            print(f"🗣  Filler (cached) — playing instantly")
            play_audio(filler_audio)
            filler_ready_ms = 0
        else:
            filler_ready_ms = 0

        # ── 5. Nova (English in, English out) ────────────────────────────────
        if has_aws:
            print("🤖 Nova (EN): ", end="", flush=True)
            english_response, ttft_ms, nova_total_ms = run_nova(english_transcript, history)
            print(f"\n   ⚡ TTFT: {ttft_ms:.0f}ms | Total: {nova_total_ms:.0f}ms")
            print(f"   EN: {english_response!r}\n")
        else:
            english_response = "I am sorry, Nova is not available right now."
            ttft_ms = nova_total_ms = 0

        # ── 6. Translate response back to farmer's language ───────────────────
        if not is_english and english_response:
            print("🔄 Translating response...", end=" ", flush=True)
            t_tr2 = time.perf_counter()
            final_response = sarvam_translate(english_response, "en-IN", lang)
            tr_out_ms = (time.perf_counter() - t_tr2) * 1000
            print(f"done ({tr_out_ms:.0f}ms)")
            print(f"   {lang}: {final_response!r}\n")
        else:
            final_response = english_response
            tr_out_ms = 0

        # ── 7. WebSocket streaming TTS — first audio in ~400ms, plays as chunks arrive
        print(f"🔊 Speaking (streaming)...")
        total_tts_ms, ttfa_tts_ms = run_tts_streaming(final_response, lang)
        print(f"   First audio: {ttfa_tts_ms:.0f}ms | Total: {total_tts_ms:.0f}ms")

        # ── 8. Latency summary ────────────────────────────────────────────────
        total_ms = (time.perf_counter() - t_turn_start) * 1000
        time_to_first_audio = asr_ms  # filler is cached → plays right after ASR

        print()
        print("┌─ Latency breakdown ──────────────────────────┐")
        print(f"│  ASR + translate (→EN)   : {asr_ms:>7.0f} ms         │")
        print(f"│  Filler (cached)         :       0 ms         │")
        if has_aws:
            print(f"│  Nova TTFT               : {ttft_ms:>7.0f} ms         │")
            print(f"│  Nova total              : {nova_total_ms:>7.0f} ms         │")
        if not is_english:
            print(f"│  Translate out (→{lang[:2].upper()})     : {tr_out_ms:>7.0f} ms         │")
        print(f"│  Response TTS            : {total_tts_ms:>7.0f} ms         │")
        print(f"│  ──────────────────────────────────────────  │")
        print(f"│  Time to first audio     : {time_to_first_audio:>7.0f} ms         │")
        print(f"│  Full turn               : {total_ms:>7.0f} ms         │")
        print("└──────────────────────────────────────────────┘")
        print()

        # Store English conversation in history for multi-turn context
        if has_aws and english_response and not english_response.startswith("["):
            history.append({"role": "user", "content": [{"text": english_transcript}]})
            history.append({"role": "assistant", "content": [{"text": english_response}]})


if __name__ == "__main__":
    main()
