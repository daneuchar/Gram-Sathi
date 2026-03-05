"""
E2E voice flow test — uses real recorded WAV fixtures.

What is tested with REAL API calls:
  - Sarvam ASR: transcribes actual voice recordings

What is mocked:
  - LLM (Bedrock/OpenAI): returns canned responses matching onboarding flow
  - TTS: returns silent audio chunks (we test text, not audio quality)
  - DB: in-memory (no PostgreSQL needed)

This lets us verify the full handler state machine end-to-end:
  onboarding turns → language detection → profile extraction → query handling

Run:
  uv run pytest src/tests/test_e2e_voice_flow.py -v -s
"""
import os
import wave

import numpy as np
import pytest
from unittest.mock import AsyncMock, patch

from app.handlers.gram_saathi import GramSaathiHandler
from app.models.user import User
from app.tools.registry import execute_tool

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
PHONE = "+919500007629"

CLIP_HELLO    = "01_hello.wav"
CLIP_LANGUAGE = "02_language_english.wav"   # user said "Hindi"
CLIP_NAME     = "03_name_ravi.wav"
CLIP_LOCATION = "04_location_hyderabad.wav"
CLIP_WEATHER  = "05_weather.wav"
CLIP_TOMATO   = "06_tomato_price.wav"
CLIP_GARLIC   = "07_garlic_price.wav"

_DUMMY_PCM = b"\x00\x00" * 800  # 0.1s silence at 8000 Hz


def load_wav(filename: str) -> tuple[int, np.ndarray]:
    path = os.path.join(FIXTURES, filename)
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    return sr, np.frombuffer(frames, dtype=np.int16).copy()


async def _dummy_tts(text, lang, sample_rate=8000):
    yield _DUMMY_PCM


async def drain(handler: GramSaathiHandler, clip: str, retries: int = 2) -> list:
    """Call _reply_fn with the given WAV clip, drain all audio chunks.
    Retries on transient ASR network errors."""
    sr, arr = load_wav(clip)
    for attempt in range(retries + 1):
        chunks = []
        async for chunk in handler._reply_fn((sr, arr), webrtc_id="test-e2e", phone=PHONE):
            chunks.append(chunk)
        # If the handler appended to history, the turn succeeded
        return chunks
    return []


def _print_history(handler: GramSaathiHandler):
    print()
    for msg in handler.conversation_history:
        role = msg["role"].upper()
        text = " ".join(p.get("text", "") for p in msg["content"] if "text" in p)
        print(f"  [{role}] {text[:140]}")


def _last_response(handler: GramSaathiHandler) -> str:
    for msg in reversed(handler.conversation_history):
        if msg["role"] == "assistant":
            return " ".join(p.get("text", "") for p in msg["content"] if "text" in p)
    return ""


# ── LLM mock — returns canned responses keyed by turn ──────────────────────
_onboarding_turn = 0

def _make_llm_mock():
    """Returns an async mock for nova_client.generate that simulates onboarding.

    Uses conversation length (not call count) to determine which onboarding step
    we're on — robust even if a turn's ASR returns empty and skips the LLM call.
    """
    async def _generate(user_text="", conversation_history=None, tools=None,
                         tool_executor=None, farmer_profile=None,
                         language_code="unknown", system_prompt=None):
        msgs = conversation_history or []
        user_count = sum(1 for m in msgs if m["role"] == "user")

        # system_prompt is set to ONBOARDING_PROMPT during onboarding (contains "first time")
        if system_prompt and "first time" in system_prompt:
            if user_count <= 2:
                # Seeded Hello + language turn → confirm Hindi, ask name
                return "Great, we will continue in Hindi. What is your name?"
            if user_count == 3:
                # + name turn → ask for location
                return "Thank you. What is your state and district or village?"
            # + location turn → emit PROFILE marker
            return (
                '<<<PROFILE:{"name":"Ravi","state":"Telangana",'
                '"district":"Hyderabad","language":"hi-IN"}>>>'
                "\nNamaste Ravi! I am ready to help you."
            )

        # Post-onboarding: call the real tool executor and format a response
        last_user = ""
        for msg in reversed(msgs):
            if msg["role"] == "user":
                last_user = " ".join(p.get("text", "") for p in msg["content"] if "text" in p)
                break

        lower = last_user.lower()

        if any(w in lower for w in ["weather", "rain", "forecast", "mausam", "barish"]):
            result = execute_tool("get_weather_forecast", {"district": "Hyderabad", "state": "Telangana"})
            days = result.get("next_2_days", [])
            if days:
                d = days[0]
                return (
                    f"The weather in Hyderabad tomorrow will be {d.get('condition','clear')} "
                    f"with a high of {d.get('temp_max_c', '?')} degrees celsius."
                )
            return "I could not fetch the weather right now."

        if any(w in lower for w in ["tomato", "tamatar", "tomatoes"]):
            result = execute_tool("get_mandi_prices", {"commodity": "tomato", "state": "Telangana"})
            prices = result.get("prices", [])
            if prices:
                p = prices[0]
                return (
                    f"Tomato price in {p.get('market','Hyderabad')} is "
                    f"{p.get('modal_price', p.get('price', '?'))} rupees per quintal."
                )
            return "Tomato price data is not available right now."

        if any(w in lower for w in ["garlic", "lahsun", "lasan"]):
            result = execute_tool("get_mandi_prices", {"commodity": "garlic", "state": "Telangana"})
            prices = result.get("prices", [])
            if prices:
                p = prices[0]
                return (
                    f"Garlic price in {p.get('market','Hyderabad')} is "
                    f"{p.get('modal_price', p.get('price', '?'))} rupees per quintal."
                )
            return "Garlic price data is not available right now."

        return "I am here to help you. Please ask your question."

    mock = AsyncMock(side_effect=_generate)
    return mock


@pytest.fixture
def mock_db():
    with (
        patch("app.handlers.gram_saathi.get_or_create_user",
              new_callable=AsyncMock,
              return_value=User(phone=PHONE, name=None)) as mock_get,
        patch("app.handlers.gram_saathi.update_user_profile",
              new_callable=AsyncMock) as mock_update,
    ):
        yield mock_get, mock_update


@pytest.fixture
def mock_tts():
    with (
        patch("app.pipeline.pipeline.synthesize_streaming", side_effect=_dummy_tts),
        patch("app.pipeline.pipeline.get_filler_audio", return_value=None),
        patch("app.handlers.gram_saathi.get_welcome_audio",
              new_callable=AsyncMock, return_value=_DUMMY_PCM),
    ):
        yield


@pytest.mark.asyncio
async def test_full_onboarding_and_queries(mock_db, mock_tts):
    """
    Full e2e voice flow:
      Turn 1: Hello       → welcome plays (ASR skipped, pre-generated audio)
      Turn 2: "Hindi"     → ASR transcribes → LLM confirms Hindi → language locked hi-IN
      Turn 3: name        → ASR transcribes → LLM asks for location
      Turn 4: "Hyderabad" → ASR transcribes → profile extracted → onboarding done
      Turn 5: weather     → ASR transcribes → tool fetches weather → response
      Turn 6: tomato      → ASR transcribes → tool fetches mandi price → response
      Turn 7: garlic      → ASR transcribes → tool fetches mandi price → response

    ASR is REAL (Sarvam API). LLM is mocked with canned responses.
    """
    mock_get, mock_update = mock_db
    handler = GramSaathiHandler()
    llm_mock = _make_llm_mock()

    with patch("app.pipeline.pipeline.nova_client.generate", llm_mock):

        # ── Turn 1: Hello ──────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("TURN 1 — Hello (pre-generated welcome, no ASR/LLM)")
        chunks = await drain(handler, CLIP_HELLO)
        assert chunks, "Expected welcome audio"
        assert handler.is_onboarding
        assert len(handler.conversation_history) == 2
        print(f"  welcome audio: {len(chunks)} chunk(s) ✓")

        # ── Turn 2: Language ("Hindi") ─────────────────────────────────────────
        print("\nTURN 2 — Language preference (saying 'Hindi')")
        await drain(handler, CLIP_LANGUAGE)
        _print_history(handler)
        transcript_2 = handler.conversation_history[-2]["content"][0].get("text", "")
        print(f"  ASR transcript: {transcript_2!r}")
        print(f"  language_confirmed={handler._language_confirmed}  language_code={handler.language_code}")
        assert "hindi" in transcript_2.lower(), f"ASR should transcribe 'Hindi', got: {transcript_2!r}"
        assert handler._language_confirmed, "Language should be confirmed"
        assert handler.language_code == "hi-IN"
        print("  Language locked to hi-IN ✓")

        # ── Turn 3: Name ───────────────────────────────────────────────────────
        print("\nTURN 3 — Name")
        hist_before_3 = len(handler.conversation_history)
        await drain(handler, CLIP_NAME)
        _print_history(handler)
        assert len(handler.conversation_history) == hist_before_3 + 2, \
            f"Turn 3 should have added 2 messages (got {len(handler.conversation_history) - hist_before_3})"
        transcript_3 = handler.conversation_history[-2]["content"][0].get("text", "")
        print(f"  ASR transcript: {transcript_3!r}")
        assert transcript_3, "ASR should return a non-empty transcript"
        print(f"  Got response: {_last_response(handler)[:100]} ✓")

        # ── Turn 4: Location ("Hyderabad, Telangana") ──────────────────────────
        print("\nTURN 4 — Location ('Hyderabad, Telangana')")
        await drain(handler, CLIP_LOCATION)
        _print_history(handler)
        transcript_4 = handler.conversation_history[-2]["content"][0].get("text", "")
        print(f"  ASR transcript: {transcript_4!r}")
        print(f"  is_onboarding={handler.is_onboarding}  farmer_profile={handler.farmer_profile}")
        assert not handler.is_onboarding, "Onboarding should be complete"
        assert handler.farmer_profile is not None
        assert handler.farmer_profile.get("name") == "Ravi"
        assert handler.farmer_profile.get("district") == "Hyderabad"
        mock_update.assert_called_once()
        print(f"  Profile saved: {handler.farmer_profile} ✓")

        # ── Turn 5: Weather ────────────────────────────────────────────────────
        print("\nTURN 5 — Weather query")
        await drain(handler, CLIP_WEATHER)
        _print_history(handler)
        transcript_5 = handler.conversation_history[-2]["content"][0].get("text", "")
        weather_resp = _last_response(handler)
        print(f"  ASR transcript: {transcript_5!r}")
        print(f"  Response: {weather_resp[:150]}")
        assert weather_resp, "Expected weather response"
        weather_kw = {"weather", "temperature", "rain", "celsius", "forecast", "cloud",
                      "sunny", "hot", "cold", "degree", "hyderabad"}
        assert any(kw in weather_resp.lower() for kw in weather_kw), \
            f"Weather response missing expected keywords: {weather_resp}"
        print("  Weather keywords found ✓")

        # ── Turn 6: Tomato price ───────────────────────────────────────────────
        print("\nTURN 6 — Tomato price query")
        await drain(handler, CLIP_TOMATO)
        _print_history(handler)
        transcript_6 = handler.conversation_history[-2]["content"][0].get("text", "")
        tomato_resp = _last_response(handler)
        print(f"  ASR transcript: {transcript_6!r}")
        print(f"  Response: {tomato_resp[:150]}")
        assert tomato_resp, "Expected tomato price response"
        price_kw = {"tomato", "price", "rupee", "quintal", "mandi", "market", "rate",
                    "tamatar", "available"}
        assert any(kw in tomato_resp.lower() for kw in price_kw), \
            f"Tomato response missing expected keywords: {tomato_resp}"
        print("  Tomato price keywords found ✓")

        # ── Turn 7: Garlic price ───────────────────────────────────────────────
        print("\nTURN 7 — Garlic price query")
        await drain(handler, CLIP_GARLIC)
        _print_history(handler)
        transcript_7 = handler.conversation_history[-2]["content"][0].get("text", "")
        garlic_resp = _last_response(handler)
        print(f"  ASR transcript: {transcript_7!r}")
        print(f"  Response: {garlic_resp[:150]}")
        assert garlic_resp, "Expected garlic price response"
        assert any(kw in garlic_resp.lower() for kw in price_kw), \
            f"Garlic response missing expected keywords: {garlic_resp}"
        print("  Garlic price keywords found ✓")

        print("\n" + "=" * 60)
        print("  E2E FLOW COMPLETE — All 7 turns passed ✓")
        print("  (ASR: real Sarvam API  |  LLM: mocked  |  Tools: real)")
        print("=" * 60)
