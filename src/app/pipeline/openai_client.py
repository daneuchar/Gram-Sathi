"""OpenAI chat client with the same generate() interface as NovaClient.

Handles message format conversion from Bedrock format (used internally in
conversation_history) to OpenAI format, and tool format conversion from
Bedrock toolSpec format to OpenAI function format.
"""
import json
import logging

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


def _to_openai_tools(nova_tools: list[dict]) -> list[dict]:
    """Convert Bedrock toolSpec format → OpenAI function format."""
    result = []
    for t in nova_tools:
        spec = t["toolSpec"]
        result.append({
            "type": "function",
            "function": {
                "name": spec["name"],
                "description": spec["description"],
                "parameters": spec["inputSchema"]["json"],
            },
        })
    return result


def _to_openai_messages(messages: list[dict]) -> list[dict]:
    """Convert Bedrock-format conversation history → OpenAI message list."""
    result = []
    for msg in messages:
        role = msg["role"]
        parts = msg["content"]

        # Tool results: user turn containing toolResult blocks
        if role == "user" and parts and "toolResult" in parts[0]:
            for part in parts:
                tr = part["toolResult"]
                raw = tr.get("content", [])
                content_str = json.dumps(raw[0]["json"]) if raw and "json" in raw[0] else str(raw)
                result.append({
                    "role": "tool",
                    "tool_call_id": tr["toolUseId"],
                    "content": content_str,
                })
            continue

        # Assistant turn that made tool calls
        if role == "assistant" and any("toolUse" in p for p in parts):
            tool_calls = []
            text_parts = []
            for part in parts:
                if "toolUse" in part:
                    tu = part["toolUse"]
                    tool_calls.append({
                        "id": tu["toolUseId"],
                        "type": "function",
                        "function": {
                            "name": tu["name"],
                            "arguments": json.dumps(tu["input"]),
                        },
                    })
                elif "text" in part:
                    text_parts.append(part["text"])
            entry: dict = {"role": "assistant", "tool_calls": tool_calls}
            if text_parts:
                entry["content"] = " ".join(text_parts)
            result.append(entry)
            continue

        # Plain text turn
        text = " ".join(p.get("text", "") for p in parts if "text" in p)
        result.append({"role": role, "content": text})

    return result


class OpenAIClient:
    def __init__(self):
        self.model = settings.llm_model
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

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
        from app.pipeline.nova_client import SYSTEM_PROMPT

        messages: list[dict] = list(conversation_history or [])
        if user_text:
            messages.append({"role": "user", "content": [{"text": user_text}]})

        openai_messages = [
            {"role": "system", "content": system_prompt or SYSTEM_PROMPT}
        ] + _to_openai_messages(messages)

        openai_tools = _to_openai_tools(tools) if tools else None

        for _ in range(5):  # max tool rounds
            kwargs: dict = {
                "model": self.model,
                "messages": openai_messages,
                "max_tokens": 512,
                "temperature": 0.3,
            }
            if openai_tools:
                kwargs["tools"] = openai_tools

            response = await self._client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            if choice.finish_reason == "tool_calls" and tool_executor is not None:
                tool_calls = choice.message.tool_calls
                # Append assistant message with tool_calls (model_dump gives dict)
                openai_messages.append(choice.message.model_dump(exclude_unset=True))
                for tc in tool_calls:
                    result = tool_executor(tc.function.name, json.loads(tc.function.arguments))
                    openai_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    })
            else:
                return choice.message.content or ""

        return ""
