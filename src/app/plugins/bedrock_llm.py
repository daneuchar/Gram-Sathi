"""AWS Bedrock LLM plugin for LiveKit Agents — non-streaming Converse API.

The official livekit-plugins-aws uses ConverseStream which doesn't support
tool use with Llama models. This plugin uses the non-streaming Converse API
and builds messages directly from ChatContext items to satisfy Bedrock's
strict message ordering rules for Llama.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import boto3
from livekit.agents import llm
from livekit.agents.llm import (
    ChatChunk,
    ChatContext,
    ChatMessage,
    ChoiceDelta,
    FunctionCall,
    FunctionCallOutput,
    FunctionToolCall,
)
from livekit.agents.llm._provider_format.aws import to_fnc_ctx
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

from app.config import settings

_THINKING_RE = re.compile(r'<thinking>.*?</thinking>\s*', re.DOTALL)

logger = logging.getLogger(__name__)


def _strip_thinking(text: str) -> str:
    """Remove <thinking>...</thinking> chain-of-thought blocks."""
    return _THINKING_RE.sub("", text).strip()


def _build_bedrock_messages(chat_ctx: ChatContext) -> tuple[list[dict], str]:
    """Convert ChatContext items to Bedrock Converse messages + system string.

    Bedrock (especially with Llama) requires:
    - Strict user/assistant alternation
    - toolUse in assistant messages, toolResult in user messages
    - No mixing of text and toolResult in the same user message
    - toolResult count must match toolUse count in the preceding assistant turn
    """
    system_parts: list[str] = []
    messages: list[dict] = []

    for item in chat_ctx.items:
        if isinstance(item, ChatMessage):
            if item.role in ("system", "developer"):
                text = item.text_content or ""
                if text:
                    system_parts.append(text)
                continue

            role = "assistant" if item.role == "assistant" else "user"
            text = item.text_content or ""
            if not text:
                continue

            # Merge into previous message of same role, but NEVER mix text
            # with toolUse/toolResult blocks — Bedrock rejects mixed turns.
            if messages and messages[-1]["role"] == role:
                prev_content = messages[-1]["content"]
                has_tool_blocks = any(
                    "toolUse" in p or "toolResult" in p for p in prev_content
                )
                if has_tool_blocks:
                    # Can't merge text into a tool turn — start a new message
                    messages.append({"role": role, "content": [{"text": text}]})
                else:
                    prev_content.append({"text": text})
            else:
                messages.append({"role": role, "content": [{"text": text}]})

        elif isinstance(item, FunctionCall):
            # toolUse goes in an assistant message
            try:
                args = json.loads(item.arguments or "{}")
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_use_block = {
                "toolUse": {
                    "toolUseId": item.call_id,
                    "name": item.name,
                    "input": args,
                }
            }
            if messages and messages[-1]["role"] == "assistant":
                messages[-1]["content"].append(tool_use_block)
            else:
                messages.append({"role": "assistant", "content": [tool_use_block]})

        elif isinstance(item, FunctionCallOutput):
            # toolResult goes in a user message
            try:
                output = json.loads(item.output) if isinstance(item.output, str) else item.output
                result_content = [{"json": output}] if isinstance(output, dict) else [{"text": str(output)}]
            except (json.JSONDecodeError, TypeError):
                result_content = [{"text": item.output}]

            tool_result_block = {
                "toolResult": {
                    "toolUseId": item.call_id,
                    "content": result_content,
                    "status": "error" if item.is_error else "success",
                }
            }
            # toolResult must be in a user message, never mixed with text
            if messages and messages[-1]["role"] == "user" and all("toolResult" in p for p in messages[-1]["content"]):
                # Previous user message is all toolResults — safe to append
                messages[-1]["content"].append(tool_result_block)
            else:
                messages.append({"role": "user", "content": [tool_result_block]})

    # Ensure first message is user (Bedrock requirement)
    if not messages or messages[0]["role"] != "user":
        messages.insert(0, {"role": "user", "content": [{"text": "(start)"}]})

    # Ensure strict alternation — insert filler messages where needed
    fixed: list[dict] = [messages[0]]
    for msg in messages[1:]:
        if msg["role"] == fixed[-1]["role"]:
            # Same role twice — insert a filler for the other role
            filler_role = "assistant" if msg["role"] == "user" else "user"
            fixed.append({"role": filler_role, "content": [{"text": "..."}]})
        fixed.append(msg)

    system = "\n".join(system_parts)
    return fixed, system


class _BedrockLLMStream(llm.LLMStream):
    """Wraps a Bedrock Converse call as a LiveKit LLMStream."""

    def __init__(
        self,
        llm_instance: BedrockLLM,
        chat_ctx: ChatContext,
        tools: list[llm.Tool],
    ) -> None:
        super().__init__(
            llm_instance,
            chat_ctx=chat_ctx,
            tools=tools,
            conn_options=DEFAULT_API_CONNECT_OPTIONS,
        )

    async def _run(self) -> None:
        messages, system_text = _build_bedrock_messages(self._chat_ctx)

        kwargs: dict[str, Any] = {
            "modelId": settings.bedrock_model_id,
            "messages": messages,
            "inferenceConfig": {"maxTokens": 2048, "temperature": 0.2},
        }
        if system_text:
            kwargs["system"] = [{"text": system_text}]

        if self._tools:
            tool_ctx = llm.ToolContext(self._tools)
            tool_specs = to_fnc_ctx(tool_ctx)
            if tool_specs:
                kwargs["toolConfig"] = {"tools": tool_specs}

        logger.info("[bedrock] calling converse: %d tools, %d messages", len(self._tools), len(messages))
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda k=kwargs: self._llm._client.converse(**k)
            )
        except Exception as exc:
            err_str = str(exc)
            if "tool use" in err_str.lower() or "toolconfig" in err_str.lower():
                # Model doesn't support tool use — retry without tools
                logger.warning("[bedrock] model does not support tool use, retrying without toolConfig: %s", exc)
                kwargs.pop("toolConfig", None)
                response = await asyncio.get_event_loop().run_in_executor(
                    None, lambda k=kwargs: self._llm._client.converse(**k)
                )
            else:
                raise
        output_msg = response.get("output", {}).get("message", {})
        parts = output_msg.get("content", [])
        stop_reason = response.get("stopReason", "")
        logger.info("[bedrock] stopReason=%s, parts=%d", stop_reason, len(parts))

        if stop_reason == "tool_use":
            for part in parts:
                if "toolUse" in part:
                    tool_use = part["toolUse"]
                    self._event_ch.send_nowait(
                        ChatChunk(
                            id="bedrock-0",
                            delta=ChoiceDelta(
                                role="assistant",
                                tool_calls=[FunctionToolCall(
                                    type="function",
                                    name=tool_use["name"],
                                    arguments=json.dumps(tool_use.get("input", {})),
                                    call_id=tool_use["toolUseId"],
                                )],
                            ),
                        )
                    )
                elif "text" in part:
                    logger.debug("[bedrock] suppressing pre-tool text: %s", part["text"][:100])
        else:
            text = " ".join(p["text"] for p in parts if "text" in p)
            text = _strip_thinking(text)
            logger.debug("[bedrock] response text (%d chars): %s", len(text), text[:200])
            if text:
                self._event_ch.send_nowait(
                    ChatChunk(
                        id="bedrock-0",
                        delta=ChoiceDelta(role="assistant", content=text),
                    )
                )


class BedrockLLM(llm.LLM):
    """LiveKit LLM plugin backed by AWS Bedrock (non-streaming Converse)."""

    def __init__(self) -> None:
        super().__init__()
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=settings.bedrock_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )

    def chat(
        self,
        *,
        chat_ctx: ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options=DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls=None,
        tool_choice=None,
        extra_kwargs=None,
    ) -> _BedrockLLMStream:
        return _BedrockLLMStream(self, chat_ctx=chat_ctx, tools=tools or [])
