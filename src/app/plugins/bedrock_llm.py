"""AWS Bedrock LLM plugin for LiveKit Agents — uses Llama 3.3 70B via Converse API."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import boto3
from livekit.agents import llm
from livekit.agents.llm import ChatChunk, ChoiceDelta
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

from app.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are Gram Saathi, a helpful voice assistant for Indian farmers.

Language:
- Always respond in English. The system will translate to the farmer's language.
- Use simple, clear spoken English suitable for phone conversations.

Response Style:
- This is a PHONE CALL. Keep every response to ONE or TWO short sentences maximum.
- Never explain, elaborate, or add follow-up offers. Answer only what was asked.
- Never use markdown formatting — no asterisks, bullet points, headers, or symbols. Plain text only.

Accuracy:
- Always use available tools for real-time data such as prices, weather, or government schemes.
- Never guess or fabricate factual information.
- If data is unavailable, say: "That information is not available right now."
- If outside farming topics, say: "I can only help with farming questions."

Number Formatting:
- Always spell out numbers in English words.
- Say "twelve hundred rupees" not "1200 rupees". Say "twenty five percent" not "25%".

Tone:
- Be polite, supportive, and respectful to farmers.
"""


class _BedrockLLMStream(llm.LLMStream):
    """Wraps a Bedrock Converse call as a LiveKit LLMStream."""

    def __init__(
        self,
        llm_instance: BedrockLLM,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
    ) -> None:
        super().__init__(
            llm_instance,
            chat_ctx=chat_ctx,
            tools=tools,
            conn_options=DEFAULT_API_CONNECT_OPTIONS,
        )

    async def _run(self) -> None:
        messages, system = _build_bedrock_messages(self._chat_ctx)
        kwargs: dict[str, Any] = {
            "modelId": settings.llama_model_id,
            "system": [{"text": system}],
            "messages": messages,
            "inferenceConfig": {"maxTokens": 256, "temperature": 0.3},
        }

        response = await asyncio.get_event_loop().run_in_executor(
            None, lambda k=kwargs: self._llm._client.converse(**k)
        )
        output_msg = response.get("output", {}).get("message", {})
        parts = output_msg.get("content", [])

        text = " ".join(p["text"] for p in parts if "text" in p)
        self._event_ch.send_nowait(
            ChatChunk(
                id="bedrock-0",
                delta=ChoiceDelta(role="assistant", content=text),
            )
        )


class BedrockLLM(llm.LLM):
    """LiveKit LLM plugin backed by AWS Bedrock (Llama 3.3 70B)."""

    def __init__(self) -> None:
        super().__init__()
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_default_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options=DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls=None,
        tool_choice=None,
        extra_kwargs=None,
    ) -> _BedrockLLMStream:
        return _BedrockLLMStream(self, chat_ctx=chat_ctx, tools=tools or [])


def _build_bedrock_messages(chat_ctx: llm.ChatContext) -> tuple[list[dict], str]:
    """Convert LiveKit ChatContext to Bedrock Converse messages + system string."""
    system = _SYSTEM_PROMPT
    messages: list[dict] = []

    for msg in chat_ctx.messages():
        if msg.role == "system":
            # content is a list of items; extract text
            text = msg.content[0] if isinstance(msg.content, list) and msg.content else str(msg.content)
            system = str(text)
            continue
        role = "user" if msg.role == "user" else "assistant"
        text = msg.content[0] if isinstance(msg.content, list) and msg.content else str(msg.content)
        messages.append({"role": role, "content": [{"text": str(text)}]})

    return messages, system
