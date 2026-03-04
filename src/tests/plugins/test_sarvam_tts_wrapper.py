"""Tests for SarvamTTS pre-processing utilities."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_prepare_tts_text_strips_markdown():
    from app.plugins.sarvam_tts_wrapper import prepare_tts_text

    result = await prepare_tts_text("**Price is 1200 rupees**", "en-IN")
    assert "*" not in result
    assert "one thousand" in result


@pytest.mark.asyncio
async def test_prepare_tts_text_translates_for_hindi():
    from app.plugins.sarvam_tts_wrapper import prepare_tts_text

    with patch("app.plugins.sarvam_tts_wrapper.from_english", new_callable=AsyncMock) as mock_trans:
        mock_trans.return_value = "गेहूं की कीमत बारह सौ रुपये है"
        result = await prepare_tts_text("Wheat price is 1200 rupees", "hi-IN")

    mock_trans.assert_called_once()
    assert result == "गेहूं की कीमत बारह सौ रुपये है"


@pytest.mark.asyncio
async def test_prepare_tts_text_skips_translate_for_english():
    from app.plugins.sarvam_tts_wrapper import prepare_tts_text

    with patch("app.plugins.sarvam_tts_wrapper.from_english", new_callable=AsyncMock) as mock_trans:
        result = await prepare_tts_text("Hello farmer", "en-IN")

    mock_trans.assert_not_called()
    assert result == "Hello farmer"
