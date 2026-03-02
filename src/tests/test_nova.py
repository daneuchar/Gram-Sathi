import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.pipeline.nova_client import NovaClient
from app.pipeline.pipeline import process_turn


def test_nova_client_initializes():
    client = NovaClient()
    assert "nova" in client.model_id


@pytest.mark.asyncio
async def test_nova_generates_response():
    client = NovaClient()
    mock_response = {
        "output": {
            "message": {
                "content": [{"text": "Wheat price is 2200 per quintal."}]
            }
        }
    }
    with patch.object(client, "_call_bedrock", new_callable=AsyncMock, return_value=mock_response):
        result = await client.generate("What is the price of wheat?")
        assert result
        assert "Wheat" in result or "wheat" in result or len(result) > 0


@pytest.mark.asyncio
async def test_pipeline_handles_empty_audio():
    transcript, detected_lang, assistant_response = await process_turn(
        audio_bytes=b"",
        farmer_profile=None,
        conversation_history=[],
        language_code="hi-IN",
    )
    assert transcript == ""
    assert detected_lang == "hi-IN"
    assert assistant_response == ""
