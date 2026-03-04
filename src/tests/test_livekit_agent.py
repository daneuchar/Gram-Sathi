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
async def test_translating_tts_calls_prepare_and_delegates():
    from app.plugins.translating_tts import TranslatingTTS

    mock_inner_tts = MagicMock()
    mock_stream = MagicMock()
    mock_inner_tts.synthesize.return_value = mock_stream

    tts = TranslatingTTS(inner_tts=mock_inner_tts, language="hi-IN")

    with patch("app.plugins.translating_tts.prepare_tts_text", new_callable=AsyncMock) as mock_prep:
        mock_prep.return_value = "गेहूं की कीमत बारह सौ रुपये है"
        result = await tts.synthesize_translated("Wheat price is twelve hundred rupees")

    mock_prep.assert_called_once_with("Wheat price is twelve hundred rupees", "hi-IN")
    mock_inner_tts.synthesize.assert_called_once_with("गेहूं की कीमत बारह सौ रुपये है")


def test_classify_filler_mandi():
    from app.livekit_agent import classify_filler_for_transcript
    assert classify_filler_for_transcript("what is the wheat price in mandi") == "mandi"


def test_classify_filler_weather():
    from app.livekit_agent import classify_filler_for_transcript
    assert classify_filler_for_transcript("will it rain tomorrow") == "weather"


def test_classify_filler_generic():
    from app.livekit_agent import classify_filler_for_transcript
    assert classify_filler_for_transcript("tell me something about farming") == "generic"


def test_classify_filler_none_for_short():
    from app.livekit_agent import classify_filler_for_transcript
    assert classify_filler_for_transcript("ok") == "none"
