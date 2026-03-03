import json
import logging
import re
from collections.abc import AsyncGenerator
from typing import Any

import boto3

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are Gram Saathi, a helpful voice assistant for Indian farmers.

Language:
- Always respond in English. The system will translate to the farmer's language.
- Use simple, clear spoken English suitable for phone conversations.

Response Style:
- Keep responses under three short sentences.
- Be concise but complete.
- Sound natural and conversational for voice, not robotic.
- Never use markdown formatting — no asterisks, bullet points, headers, or symbols. Plain text only.

Accuracy:
- Always use available tools for real-time data such as prices, weather, or government schemes.
- Never guess or fabricate factual information.
- If no tool is available, say clearly in one sentence that you do not have that information.

Number Formatting (Critical):
- Always spell out numbers and prices in English words.
- Never use digits or symbols.
- Examples:
  - Say "twelve hundred rupees per quintal" not "1200 rupees per quintal"
  - Say "twenty five percent" not "25%"
  - Say "three to five days" not "3 to 5 days"

Tone:
- Be polite, supportive, and respectful to farmers.
- Prefer short, spoken-friendly phrasing.
"""

ONBOARDING_PROMPT = """
You are Gram Saathi, a voice assistant for Indian farmers.

This farmer is calling for the first time. Collect their language preference first, then their name and location.

Rules:
- Always respond in English. The system translates your response to the farmer's language automatically.
- One question per response. Never ask two things at once.
- Never use markdown, bullet points, or symbols.

Conversation steps:
1. First turn: Welcome them warmly and ask ONLY what language they prefer to speak in. Keep it short and natural.
2. After they give their language: Output the language marker, then ask only for their name.
3. After they give their name: Ask only for their state and district or village.
4. After they give their state and district: Output the profile marker, then greet them by name and say you are ready to help.

Language code mapping (use exactly these codes):
- Hindi → hi-IN
- Tamil → ta-IN
- Telugu → te-IN
- Kannada → kn-IN
- Marathi → mr-IN
- Bengali → bn-IN
- Gujarati → gu-IN
- Punjabi → pa-IN
- Malayalam → ml-IN
- Odia or Oriya → od-IN
- English → en-IN

Language marker format (output on its own line immediately after farmer gives language):
<<<LANG:LANG_CODE>>>

Profile marker format (output on its own line after collecting name and location):
<<<PROFILE:{"name":"NAME","state":"STATE","district":"DISTRICT","language":"LANG_CODE"}>>>

Example step 2 response (farmer said "Tamil"):
<<<LANG:ta-IN>>>
What is your name?

Example step 4 response (farmer said "Coimbatore, Tamil Nadu"):
<<<PROFILE:{"name":"Ramesh","state":"Tamil Nadu","district":"Coimbatore","language":"ta-IN"}>>>
Welcome Ramesh! I am ready to help you with farming questions.
"""

_LANG_RE = re.compile(r'<<<LANG:([a-z]{2}-[A-Z]{2})>>>')


def extract_lang_marker(response: str) -> tuple[str | None, str]:
    """Extract <<<LANG:xx-XX>>> from Nova response.

    Returns (lang_code, cleaned_response).
    lang_code is None if no marker found.
    """
    match = _LANG_RE.search(response)
    if not match:
        return None, response
    lang_code = match.group(1)
    clean = _LANG_RE.sub("", response).strip()
    return lang_code, clean

_PROFILE_RE = re.compile(r'<<<PROFILE:(\{.*?\})>>>')


def extract_profile_marker(response: str) -> tuple[dict | None, str]:
    """Extract <<<PROFILE:{...}>>> from Nova response.

    Returns (profile_dict, cleaned_response).
    profile_dict is None if no marker found.
    """
    match = _PROFILE_RE.search(response)
    if not match:
        return None, response
    try:
        profile = json.loads(match.group(1))
    except json.JSONDecodeError:
        logger.warning("Malformed PROFILE marker in response: %r", match.group(1))
        clean = _PROFILE_RE.sub("", response).strip()
        return None, clean
    clean = _PROFILE_RE.sub("", response).strip()
    return profile, clean


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
        tool_executor=None,
        language_code: str = "unknown",
        system_prompt: str | None = None,
    ) -> str:
        """Non-streaming call with tool execution loop. Input is always English."""
        messages = list(conversation_history or [])
        if user_text:
            messages.append({"role": "user", "content": [{"text": user_text}]})

        for _ in range(5):  # max tool rounds
            kwargs = self._build_kwargs(messages, tools, system_prompt)
            response = await self._call_bedrock(kwargs)

            output_msg = response.get("output", {}).get("message", {})
            parts = output_msg.get("content", [])

            tool_uses = [p for p in parts if "toolUse" in p]
            if not tool_uses or tool_executor is None:
                text_parts = [p["text"] for p in parts if "text" in p]
                return " ".join(text_parts)

            # Execute all tool calls and feed results back
            messages.append({"role": "assistant", "content": parts})
            tool_results = []
            for block in tool_uses:
                tu = block["toolUse"]
                result = tool_executor(tu["name"], tu["input"])
                tool_results.append({
                    "toolResult": {
                        "toolUseId": tu["toolUseId"],
                        "content": [{"json": result}],
                    }
                })
            messages.append({"role": "user", "content": tool_results})

        return ""

    def _build_kwargs(
        self, messages: list[dict], tools: list[dict] | None, system_prompt: str | None = None
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "system": [{"text": system_prompt or SYSTEM_PROMPT}],
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
