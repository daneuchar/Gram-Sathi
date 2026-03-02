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
import io
import os
import sys
import time
import threading
import wave
from dotenv import load_dotenv

load_dotenv()

import boto3
import httpx
import numpy as np
import sounddevice as sd

# ── Config ────────────────────────────────────────────────────────────────────
SARVAM_API_KEY  = os.environ["SARVAM_API_KEY"]
AWS_KEY         = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET      = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION      = os.environ.get("AWS_DEFAULT_REGION", "ap-south-1")
BEDROCK_MODEL   = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

SARVAM_HEADERS  = {"api-subscription-key": SARVAM_API_KEY}
RECORD_SR       = 16000   # mic sample rate
TTS_SR          = 8000    # Sarvam TTS output sample rate

FILLERS = {
    "hi-IN": "Haan ji, ek second...",
    "ta-IN": "Sari, oru nimidam...",
    "te-IN": "Avunu, okka nimisham...",
    "mr-IN": "Ho, ek kshan...",
    "default": "One moment please...",
}

SYSTEM_PROMPT = (
    "You are Gram Saathi, a voice assistant for Indian farmers. "
    "CRITICAL: Each message begins with [LANG: xx-XX]. You MUST reply ONLY in that language. "
    "If [LANG: en-IN] or [LANG: en-US], reply in English. "
    "If [LANG: hi-IN], reply in Hindi. If [LANG: ta-IN], reply in Tamil. Never switch languages. "
    "Keep replies under 3 short sentences — this is a phone call. "
    "Never fabricate prices or data — say you don't have that data if unsure."
)

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


# ── Pipeline steps ────────────────────────────────────────────────────────────

def run_asr(wav_bytes: bytes) -> tuple[str, str, float]:
    """Returns (transcript, language_code, latency_ms)."""
    t0 = time.perf_counter()
    resp = httpx.post(
        "https://api.sarvam.ai/speech-to-text",
        headers=SARVAM_HEADERS,
        data={"model": "saaras:v3", "language_code": "unknown", "with_timestamps": "false"},
        files={"file": ("audio.wav", io.BytesIO(wav_bytes), "audio/wav")},
        timeout=30,
    )
    resp.raise_for_status()
    ms = (time.perf_counter() - t0) * 1000
    d = resp.json()
    return d.get("transcript", ""), d.get("language_code", "unknown"), ms


def run_tts(text: str, lang: str) -> tuple[bytes, float]:
    """Returns (pcm_bytes, latency_ms)."""
    speaker = {"hi-IN": "anushka", "ta-IN": "anushka", "te-IN": "abhilash",
               "mr-IN": "manisha", "kn-IN": "vidya"}.get(lang, "anushka")
    t0 = time.perf_counter()
    resp = httpx.post(
        "https://api.sarvam.ai/text-to-speech",
        headers=SARVAM_HEADERS,
        json={
            "inputs": [text], "target_language_code": lang, "speaker": speaker,
            "pace": 0.9, "speech_sample_rate": TTS_SR, "model": "bulbul:v2",
            "enable_preprocessing": True,
        },
        timeout=30,
    )
    resp.raise_for_status()
    ms = (time.perf_counter() - t0) * 1000
    import base64
    return base64.b64decode(resp.json()["audios"][0]), ms


def run_nova(transcript: str, lang: str, history: list) -> tuple[str, float, float]:
    """
    Stream Nova Lite response.
    Returns (full_response, time_to_first_token_ms, total_ms).
    """
    if not has_aws:
        return "[AWS keys not set — add to .env to enable Nova]", 0, 0

    messages = list(history)
    tagged = f"[LANG: {lang}] {transcript}"
    messages.append({"role": "user", "content": [{"text": tagged}]})

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
    print()  # newline after streamed tokens
    return full_text, ttft or 0, total_ms


# ── Sentence splitter for streaming TTS ──────────────────────────────────────

def split_sentences(text: str) -> list[str]:
    import re
    parts = re.split(r'(?<=[।.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]


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

        # ── 2. ASR ────────────────────────────────────────────────────────────
        print("⏳ ASR...", end=" ", flush=True)
        transcript, lang, asr_ms = run_asr(wav)
        print(f"done ({asr_ms:.0f}ms)")
        print(f"📝 [{lang}] {transcript!r}\n")

        if not transcript.strip():
            print("⚠️  Empty transcript, try again\n"); continue

        # ── 3. Filler phrase → play immediately ───────────────────────────────
        filler = FILLERS.get(lang, FILLERS["default"])
        print(f"🗣  Playing filler: {filler!r}")
        t_filler = time.perf_counter()
        filler_audio, filler_tts_ms = run_tts(filler, lang)
        filler_ready_ms = (time.perf_counter() - t_filler) * 1000
        play_audio(filler_audio)

        # ── 4. Nova Lite (streaming) ──────────────────────────────────────────
        if has_aws:
            print("🤖 Nova response: ", end="", flush=True)
            t_nova = time.perf_counter()
            nova_response, ttft_ms, nova_total_ms = run_nova(transcript, lang, history)
            print(f"\n⚡ Nova TTFT: {ttft_ms:.0f}ms | Total: {nova_total_ms:.0f}ms\n")
        else:
            nova_response = "[Nova not available — add AWS keys]"
            ttft_ms = nova_total_ms = 0
            print(f"🤖 Nova: {nova_response}\n")

        # ── 5. TTS response → play sentence by sentence ───────────────────────
        sentences = split_sentences(nova_response)
        total_tts_ms = 0
        print("🔊 Playing response:")
        for i, sentence in enumerate(sentences):
            print(f"   [{i+1}/{len(sentences)}] {sentence!r}")
            audio_out, tts_ms = run_tts(sentence, lang)
            total_tts_ms += tts_ms
            play_audio(audio_out)

        # ── 6. Latency summary ────────────────────────────────────────────────
        total_ms = (time.perf_counter() - t_turn_start) * 1000
        time_to_first_audio = asr_ms + filler_ready_ms  # farmer hears filler first

        print()
        print("┌─ Latency breakdown ─────────────────────────┐")
        print(f"│  ASR (Sarvam Saaras v3)  : {asr_ms:>7.0f} ms        │")
        print(f"│  Filler TTS + play       : {filler_ready_ms:>7.0f} ms        │")
        if has_aws:
            print(f"│  Nova TTFT               : {ttft_ms:>7.0f} ms        │")
            print(f"│  Nova total              : {nova_total_ms:>7.0f} ms        │")
        print(f"│  Response TTS (total)    : {total_tts_ms:>7.0f} ms        │")
        print(f"│  ─────────────────────────────────────────  │")
        print(f"│  Time to first audio     : {time_to_first_audio:>7.0f} ms        │")
        print(f"│  Full turn               : {total_ms:>7.0f} ms        │")
        print("└─────────────────────────────────────────────┘")
        print()

        # Update history for multi-turn conversation
        if has_aws and nova_response and not nova_response.startswith("["):
            history.append({"role": "user", "content": [{"text": transcript}]})
            history.append({"role": "assistant", "content": [{"text": nova_response}]})


if __name__ == "__main__":
    main()
