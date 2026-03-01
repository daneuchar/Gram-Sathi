"""
End-to-end test of Sarvam AI ASR + TTS with current API.
Run: PYTHONPATH=src uv run python test_sarvam.py
"""
import base64
import httpx
import io

API_KEY = "sk_40l07iu1_wEvFAYZjrvDgeHohULWr8zGn"
HEADERS = {"api-subscription-key": API_KEY}

# Updated speakers (bulbul:v2)
TESTS = [
    {"text": "Jaipur mandi mein aaj gehun ka bhav kya hai?", "lang": "hi-IN", "speaker": "anushka"},
    {"text": "Naan oru vivasayi. En nilam rendu acre.", "lang": "ta-IN", "speaker": "anand"},
]


def test_tts(text: str, lang: str, speaker: str) -> bytes:
    print(f"\n── TTS [{lang}]: {text!r}")
    resp = httpx.post(
        "https://api.sarvam.ai/text-to-speech",
        headers=HEADERS,
        json={
            "inputs": [text],
            "target_language_code": lang,
            "speaker": speaker,
            "pace": 0.9,
            "speech_sample_rate": 8000,
            "enable_preprocessing": True,
            "model": "bulbul:v2",
        },
        timeout=30,
    )
    resp.raise_for_status()
    audio_bytes = base64.b64decode(resp.json()["audios"][0])
    print(f"   ✅ TTS OK — {len(audio_bytes):,} bytes of PCM audio")
    return audio_bytes


def test_asr(audio_bytes: bytes, lang: str) -> str:
    print(f"\n── ASR [{lang}]: sending {len(audio_bytes):,} bytes → Sarvam Saaras v3")
    resp = httpx.post(
        "https://api.sarvam.ai/speech-to-text",
        headers=HEADERS,
        data={"model": "saaras:v3", "language_code": lang, "with_timestamps": "false"},
        files={"file": ("audio.wav", io.BytesIO(audio_bytes), "audio/wav")},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    transcript = data.get("transcript", "")
    detected = data.get("language_code", lang)
    print(f"   ✅ ASR OK — detected lang: {detected}")
    print(f"   📝 Transcript: {transcript!r}")
    return transcript


if __name__ == "__main__":
    print("=" * 60)
    print("Sarvam AI — TTS + ASR end-to-end test")
    print("=" * 60)

    for test in TESTS:
        print(f"\n{'─'*60}")
        try:
            audio = test_tts(test["text"], test["lang"], test["speaker"])
            transcript = test_asr(audio, test["lang"])
        except Exception as e:
            print(f"   ❌ FAILED: {e}")

    print(f"\n{'='*60}\nDone.")
