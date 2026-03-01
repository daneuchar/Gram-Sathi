import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import boto3

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Gram Saathi, a voice assistant for Indian farmers. "
    "Always respond in the farmer's language. Keep replies under 3 sentences. "
    "Always use the provided tools to fetch real data — never guess prices, weather, or schemes."
)


class NovaClient:
    def __init__(self):
        self.model_id = settings.bedrock_model_id
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_default_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )

    async def generate_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[str | dict, None]:
        """Stream tokens from Nova Lite via converse_stream().

        Yields str tokens for text content, or dict for toolUse blocks.
        """
        kwargs = self._build_kwargs(messages, tools)
        response = await self._call_bedrock_stream(kwargs)
        stream = response.get("stream", [])

        for event in stream:
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "text" in delta:
                    yield delta["text"]
                elif "toolUse" in delta:
                    yield delta["toolUse"]
            elif "contentBlockStart" in event:
                start = event["contentBlockStart"].get("start", {})
                if "toolUse" in start:
                    yield {"toolUse": start["toolUse"]}

    async def generate(
        self,
        user_text: str,
        farmer_profile: dict | None = None,
        conversation_history: list[dict] | None = None,
        tools: list[dict] | None = None,
    ) -> str:
        """Non-streaming fallback for tool follow-ups."""
        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": [{"text": user_text}]})

        kwargs = self._build_kwargs(messages, tools)
        response = await self._call_bedrock(kwargs)

        output = response.get("output", {})
        message = output.get("message", {})
        parts = message.get("content", [])

        text_parts = [p["text"] for p in parts if "text" in p]
        return " ".join(text_parts)

    def _build_kwargs(
        self, messages: list[dict], tools: list[dict] | None
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "system": [{"text": SYSTEM_PROMPT}],
            "messages": messages,
            "inferenceConfig": {
                "maxTokens": 512,
                "temperature": 0.3,
            },
        }
        if tools:
            kwargs["toolConfig"] = {"tools": tools}
        return kwargs

    async def _call_bedrock_stream(self, kwargs: dict) -> dict:
        """Call converse_stream — runs sync boto3 in the default executor."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._client.converse_stream(**kwargs)
        )

    async def _call_bedrock(self, kwargs: dict) -> dict:
        """Call converse (non-streaming) — runs sync boto3 in the default executor."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._client.converse(**kwargs)
        )
