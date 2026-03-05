"""
Record voice fixtures for e2e tests.

Usage:
    uv run python scripts/record_test_fixtures.py

Records 6 short clips, saves to src/tests/fixtures/*.wav
Press Enter before each recording, then speak. Recording stops automatically.
"""
import wave
import sys
import os
import time

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 8000
CHANNELS = 1
DTYPE = "int16"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "tests", "fixtures")

CLIPS = [
    ("01_hello.wav",         "Say: \"Hello\" (greeting to start the call)"),
    ("02_language_english.wav", "Say: \"English\" (language preference)"),
    ("03_name_ravi.wav",     "Say: \"My name is Ravi\""),
    ("04_location_hyderabad.wav", "Say: \"Hyderabad, Telangana\""),
    ("05_weather.wav",       "Say: \"What is the weather in Hyderabad?\""),
    ("06_tomato_price.wav",  "Say: \"What is the price of tomato?\""),
    ("07_garlic_price.wav",  "Say: \"What is the price of garlic?\""),
]


def save_wav(path: str, audio: np.ndarray, sample_rate: int = SAMPLE_RATE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    print(f"  Saved → {os.path.relpath(path)}")


def record_clip(prompt: str, max_seconds: float = 5.0) -> np.ndarray:
    input(f"\n{prompt}\n  Press Enter then speak (up to {max_seconds:.0f}s)... ")
    print("  Recording... ", end="", flush=True)
    audio = sd.rec(
        int(max_seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
    )
    sd.wait()
    # Trim trailing silence (below 200 RMS for > 0.3 s)
    rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2, axis=1 if audio.ndim > 1 else None))
    # Simple trim: find last sample above threshold
    threshold = 200
    flat = audio.flatten()
    nonzero = np.where(np.abs(flat) > threshold)[0]
    if len(nonzero):
        trimmed = flat[: nonzero[-1] + int(SAMPLE_RATE * 0.2)]  # 200ms tail
    else:
        trimmed = flat
    print(f"done ({len(trimmed) / SAMPLE_RATE:.1f}s)")
    return trimmed


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=" * 60)
    print("  Gram Saathi — E2E Test Fixture Recorder")
    print("=" * 60)
    print(f"  Output dir: {os.path.relpath(OUTPUT_DIR)}")
    print(f"  Sample rate: {SAMPLE_RATE} Hz  |  Mono  |  int16")
    print("\nYou will record 7 short clips. Speak clearly after pressing Enter.")

    for filename, prompt in CLIPS:
        out_path = os.path.join(OUTPUT_DIR, filename)
        if os.path.exists(out_path):
            overwrite = input(f"\n  {filename} already exists. Re-record? [y/N] ").strip().lower()
            if overwrite != "y":
                print("  Skipped.")
                continue
        audio = record_clip(prompt)
        save_wav(out_path, audio)

    print("\n" + "=" * 60)
    print("  All fixtures recorded!")
    print("  Run the e2e tests with:")
    print("    uv run pytest src/tests/test_e2e_voice_flow.py -v")
    print("=" * 60)


if __name__ == "__main__":
    main()
