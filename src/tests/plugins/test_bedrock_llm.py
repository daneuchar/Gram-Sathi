"""Tests for BedrockLLM plugin."""
import pytest
from unittest.mock import MagicMock, patch
from livekit.agents import llm


def make_bedrock_response(text: str) -> dict:
    """Build a minimal Bedrock Converse API response dict."""
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": text}],
            }
        },
        "stopReason": "end_turn",
    }


@pytest.mark.asyncio
async def test_bedrock_llm_basic_response():
    """BedrockLLM.chat() yields a ChatChunk with the model's text."""
    from app.plugins.bedrock_llm import BedrockLLM

    mock_response = make_bedrock_response("Wheat price is one thousand rupees.")

    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.converse.return_value = mock_response

        llm_plugin = BedrockLLM()
        chat_ctx = llm.ChatContext()
        chat_ctx.add_message(role="user", content="What is the wheat price?")

        chunks = []
        async with llm_plugin.chat(chat_ctx=chat_ctx) as stream:
            async for chunk in stream:
                if chunk.delta and chunk.delta.content:
                    chunks.append(chunk.delta.content)

        assert "".join(chunks) == "Wheat price is one thousand rupees."


@pytest.mark.asyncio
async def test_bedrock_llm_system_prompt_injection():
    """BedrockLLM uses system prompt from chat context or falls back to default."""
    from app.plugins.bedrock_llm import BedrockLLM

    mock_response = make_bedrock_response("Namaste Ramesh!")

    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.converse.return_value = mock_response

        llm_plugin = BedrockLLM()
        chat_ctx = llm.ChatContext()
        chat_ctx.add_message(role="system", content="Custom system prompt.")
        chat_ctx.add_message(role="user", content="Hello")

        async with llm_plugin.chat(chat_ctx=chat_ctx) as stream:
            async for _ in stream:
                pass

        call_kwargs = mock_client.converse.call_args[1]
        assert call_kwargs["system"][0]["text"] == "Custom system prompt."
