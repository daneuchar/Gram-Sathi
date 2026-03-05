"""LiveKit Agents entrypoint for Gram Saathi."""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterable
from datetime import datetime
from typing import Any

from livekit import rtc
from livekit.agents import Agent, AgentSession, JobContext, LanguageCode, RunContext, WorkerOptions, cli
from livekit.agents.llm import ChatMessage, FunctionCall, function_tool
from livekit.agents.voice import ModelSettings
from livekit.plugins import sarvam, silero

from app.plugins.bedrock_llm import BedrockLLM

from app.config import settings
from app.database import AsyncSessionLocal, get_or_create_user, update_user_profile
from app.models.call_log import CallLog
from app.models.conversation import ConversationTurn
from app.prompts import (
    ONBOARDING_PROMPT,
    SYSTEM_PROMPT,
    extract_profile_marker,
    extract_lang_marker,
)
from app.tools.weather import get_weather_forecast as _get_weather
from app.tools.mandi import get_mandi_prices as _get_mandi
from app.tools.crop_advisory import get_crop_advisory as _get_advisory
from app.tools.schemes import check_scheme_eligibility as _check_schemes

logger = logging.getLogger(__name__)

_MARKER_RE = re.compile(r'<<<[^>]*>>>')
_THINKING_RE = re.compile(r'<thinking>.*?</thinking>\s*', re.DOTALL)


class OnboardingAgent(Agent):
    """Agent for first-time callers — no tools, just collects profile info."""

    def __init__(self, *, stt_plugin: sarvam.STT, tts_plugin: sarvam.TTS, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._stt_plugin = stt_plugin
        self._tts_plugin = tts_plugin

    async def tts_node(
        self, text: AsyncIterable[str], model_settings: ModelSettings
    ) -> AsyncIterable[rtc.AudioFrame]:
        return Agent.default.tts_node(self, _strip_markers(text, self._stt_plugin, self._tts_plugin), model_settings)


class GramSaathiAgent(Agent):
    """Main agent with tools defined as class methods (per LiveKit docs)."""

    def __init__(self, *, stt_plugin: sarvam.STT, tts_plugin: sarvam.TTS, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._stt_plugin = stt_plugin
        self._tts_plugin = tts_plugin

    @function_tool(
        description=(
            "Get a 5-day weather forecast for any district and state in India. "
            "IMPORTANT: All parameter values MUST be in English. "
            "You MUST call this tool for ANY weather question. NEVER guess weather information."
        )
    )
    async def get_weather_forecast(self, context: RunContext, district: str, state: str) -> dict:
        """Get weather forecast for a location in India.

        Args:
            district: District name in English, e.g. Hyderabad, Dharmapuri
            state: State name in English, e.g. Telangana, Tamil Nadu
        """
        return await asyncio.to_thread(_get_weather, district, state)

    @function_tool(
        description=(
            "Get current mandi (agricultural market) prices for a commodity in ANY state in India. "
            "IMPORTANT: All parameter values MUST be in English. "
            "You MUST call this tool for ANY question about crop prices. NEVER answer price questions from memory."
        )
    )
    async def get_mandi_prices(self, context: RunContext, commodity: str, state: str, district: str = "") -> dict:
        """Get mandi prices for a commodity.

        Args:
            commodity: Crop name in English, e.g. Tomato, Wheat, Rice, Onion
            state: State name in English, e.g. Telangana, Haryana, Tamil Nadu
            district: District name in English (optional). Omit if unknown.
        """
        return await asyncio.to_thread(_get_mandi, commodity, state, district or None)

    @function_tool(
        description=(
            "Get season-aware crop advisory for a given crop and state in India. "
            "IMPORTANT: All parameter values MUST be in English."
        )
    )
    async def get_crop_advisory(self, context: RunContext, crop: str, state: str) -> dict:
        """Get crop advisory information.

        Args:
            crop: Crop name in English, e.g. wheat, rice, tomato
            state: State name in English, e.g. Telangana, Haryana
        """
        return await asyncio.to_thread(_get_advisory, crop, state)

    @function_tool(
        description=(
            "Check government scheme eligibility for a farmer based on their profile. "
            "IMPORTANT: All parameter values MUST be in English."
        )
    )
    async def check_scheme_eligibility(
        self, context: RunContext, land_holding: float = 0, state: str = "", crop: str = "", category: str = ""
    ) -> dict:
        """Check scheme eligibility.

        Args:
            land_holding: Land holding in acres
            state: State name in English
            crop: Primary crop name in English
            category: Farmer category (small/marginal/large)
        """
        profile = {}
        if land_holding:
            profile["land_holding"] = land_holding
        if state:
            profile["state"] = state
        if crop:
            profile["crop"] = crop
        if category:
            profile["category"] = category
        return await asyncio.to_thread(_check_schemes, profile)

    async def tts_node(
        self, text: AsyncIterable[str], model_settings: ModelSettings
    ) -> AsyncIterable[rtc.AudioFrame]:
        return Agent.default.tts_node(self, _strip_markers(text, self._stt_plugin, self._tts_plugin), model_settings)


async def _strip_markers(
    text: AsyncIterable[str], stt_plugin: sarvam.STT, tts_plugin: sarvam.TTS
) -> AsyncIterable[str]:
    """Strip <<<...>>> markers and <thinking>...</thinking> blocks from LLM output stream."""
    buf = ""
    async for chunk in text:
        buf += chunk

        # Strip complete <thinking>...</thinking> blocks
        while "<thinking>" in buf and "</thinking>" in buf:
            start = buf.index("<thinking>")
            end = buf.index("</thinking>") + len("</thinking>")
            logger.debug("[tts_node] stripping thinking block: %s", buf[start:end][:80])
            buf = buf[:start] + buf[end:]

        # Strip complete <<<...>>> markers
        while "<<<" in buf and ">>>" in buf:
            start = buf.index("<<<")
            end = buf.index(">>>") + 3
            marker = buf[start:end]
            lang_match = re.search(r'<<<LANG:([a-z]{2}-[A-Z]{2})>>>', marker)
            if lang_match:
                lang_code = lang_match.group(1)
                logger.info("[tts_node] switching language to %s", lang_code)
                try:
                    stt_plugin._opts.language = LanguageCode(lang_code)
                except Exception:
                    pass
                try:
                    tts_plugin.update_options(target_language_code=lang_code)
                except Exception:
                    pass
            buf = buf[:start] + buf[end:]

        # Hold back incomplete tags — don't yield partial <thinking> or <<<
        hold_idx = len(buf)
        for tag_start in ("<", "<<<"):
            if tag_start in buf:
                idx = buf.index(tag_start)
                hold_idx = min(hold_idx, idx)

        if hold_idx > 0:
            yield buf[:hold_idx]
        buf = buf[hold_idx:]

    # Final cleanup of any remaining markers/thinking in buffer
    buf = _THINKING_RE.sub("", buf)
    buf = _MARKER_RE.sub("", buf).strip()
    if buf:
        yield buf


def build_system_prompt(profile: dict | None) -> str:
    """Return main system prompt with profile context, or onboarding prompt."""
    if profile is None:
        return ONBOARDING_PROMPT
    name = profile.get("name", "")
    state = profile.get("state", "")
    district = profile.get("district", "")
    lang = profile.get("language", "en-IN")
    lang_name = {
        "hi-IN": "Hindi", "ta-IN": "Tamil", "te-IN": "Telugu",
        "kn-IN": "Kannada", "mr-IN": "Marathi", "bn-IN": "Bengali",
        "gu-IN": "Gujarati", "pa-IN": "Punjabi", "ml-IN": "Malayalam",
        "od-IN": "Odia", "en-IN": "English",
    }.get(lang, "English")
    profile_ctx = (
        f"Farmer profile — Name: {name}, State: {state}, District: {district}, Language: {lang_name}. "
        f"Respond in {lang_name}. "
        f"Greet them by name ONLY on the very first turn. After that, do NOT use their name in every response. "
        f"Mix it up naturally — sometimes just answer directly, sometimes use respectful words like 'जी', 'हाँ', 'अच्छा', 'जी हाँ', 'बताती हूँ'. "
        f"Use their name only occasionally, like real phone conversations. "
        f"When the farmer asks about prices, weather, etc. WITHOUT specifying a location, default to {state}, {district}. "
        f"But if they mention ANY other state, city, or district, use THAT location — do not restrict to {state}."
    )
    return SYSTEM_PROMPT + "\n\n" + profile_ctx


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    # Resolve farmer profile from phone number
    # Try room metadata first (SIP gateway), then participant metadata (test page)
    phone = ctx.room.metadata or ""
    if not phone:
        for p in ctx.room.remote_participants.values():
            if p.metadata:
                phone = p.metadata
                break
    if not phone:
        # Wait for participant to connect and read their metadata
        try:
            participant = await asyncio.wait_for(ctx.wait_for_participant(), timeout=10)
            phone = participant.metadata or ""
        except (TimeoutError, asyncio.TimeoutError):
            pass
    logger.info("[entrypoint] resolved phone=%s", phone)
    user = await get_or_create_user(phone) if phone else None
    profile = {"name": user.name, "state": user.state, "district": user.district, "language": user.language} if user and user.name else None
    language = (profile.get("language") or "en-IN") if profile else "en-IN"
    is_onboarding = profile is None

    # STT: Sarvam streaming
    stt_plugin = sarvam.STT(
        model="saaras:v3",
        language=language,
        api_key=settings.sarvam_api_key,
    )

    # TTS: Sarvam bulbul with female voice
    tts_plugin = sarvam.TTS(
        model="bulbul:v3",
        target_language_code=language,
        speaker="priya",
        api_key=settings.sarvam_api_key,
    )

    common_kwargs = dict(
        stt_plugin=stt_plugin,
        tts_plugin=tts_plugin,
        instructions=build_system_prompt(profile),
        stt=stt_plugin,
        llm=BedrockLLM(),
        tts=tts_plugin,
        vad=silero.VAD.load(),
    )

    if is_onboarding:
        agent = OnboardingAgent(**common_kwargs)
    else:
        agent = GramSaathiAgent(**common_kwargs)

    logger.info("[entrypoint] is_onboarding=%s, agent_type=%s", is_onboarding, type(agent).__name__)

    # ── Create CallLog record ──
    call_sid = ctx.room.name
    call_start = datetime.utcnow()
    tools_used: set[str] = set()

    try:
        async with AsyncSessionLocal() as db:
            db.add(CallLog(
                call_sid=call_sid,
                phone=phone or None,
                direction="inbound",
                status="in-progress",
                language_detected=language,
            ))
            await db.commit()
        logger.info("[entrypoint] CallLog created: %s", call_sid)
    except Exception:
        logger.exception("[entrypoint] failed to create CallLog")

    session = AgentSession()

    # ── Conversation turn tracking ──
    turn_counter = 0

    async def _save_turn(speaker: str, transcript: str, tool_called: str | None = None) -> None:
        nonlocal turn_counter
        turn_counter += 1
        clean = _MARKER_RE.sub("", _THINKING_RE.sub("", transcript)).strip()
        if not clean:
            return
        try:
            async with AsyncSessionLocal() as db:
                db.add(ConversationTurn(
                    call_sid=call_sid,
                    turn_number=turn_counter,
                    speaker=speaker,
                    transcript=clean[:2000],
                    tool_called=tool_called,
                ))
                await db.commit()
        except Exception:
            logger.exception("[turns] failed to save turn %d", turn_counter)

    # Handle LANG and PROFILE markers from onboarding + save conversation turns
    async def _handle_item_added(event):
        nonlocal is_onboarding
        item = event.item

        # Save user and assistant message turns
        if isinstance(item, ChatMessage) and item.role in ("user", "assistant"):
            text = item.content[0] if isinstance(item.content, list) and item.content else ""
            text = str(text)
            if text:
                await _save_turn(item.role, text)

            # Check for END_CALL marker — auto-disconnect after farewell
            if item.role == "assistant" and "<<<END_CALL>>>" in text:
                logger.info("[end_call] END_CALL marker detected, disconnecting in 5s")
                async def _delayed_disconnect():
                    await asyncio.sleep(5)  # let TTS finish the farewell
                    try:
                        await ctx.room.disconnect()
                    except Exception:
                        logger.warning("[end_call] room disconnect failed (may already be closed)")
                asyncio.create_task(_delayed_disconnect())

            # Check for profile marker — save to DB and enable tools (assistant only)
            if item.role == "assistant":
                profile_data, _ = extract_profile_marker(text)
                if profile_data and phone:
                    await update_user_profile(
                        phone,
                        name=profile_data.get("name"),
                        state=profile_data.get("state"),
                        district=profile_data.get("district"),
                        language=profile_data.get("language"),
                    )
                    logger.info("[onboarding] profile saved for %s: %s", phone, profile_data)

                    # Switch from onboarding to main agent with tools
                    is_onboarding = False
                    new_prompt = build_system_prompt(profile_data)
                    session.update_agent(GramSaathiAgent(
                        stt_plugin=stt_plugin,
                        tts_plugin=tts_plugin,
                        instructions=new_prompt,
                        stt=stt_plugin,
                        llm=BedrockLLM(),
                        tts=tts_plugin,
                        vad=silero.VAD.load(),
                    ))
                    logger.info("[onboarding] switched to GramSaathiAgent with tools")

        # Track function calls — record tool name
        if isinstance(item, FunctionCall):
            tool_name = item.name
            tools_used.add(tool_name)
            await _save_turn("assistant", f"[Tool call: {tool_name}]", tool_called=tool_name)

    @session.on("conversation_item_added")
    def on_item_added(event):
        asyncio.create_task(_handle_item_added(event))

    # ── Finalize CallLog on room disconnect ──
    async def _finalize_call_log():
        ended = datetime.utcnow()
        duration = int((ended - call_start).total_seconds())
        try:
            async with AsyncSessionLocal() as db:
                log = await db.get(CallLog, call_sid)
                if log:
                    log.status = "completed"
                    log.ended_at = ended
                    log.duration_seconds = duration
                    log.tools_used = ",".join(sorted(tools_used)) if tools_used else None
                    await db.commit()
            logger.info("[entrypoint] CallLog finalized: %s (%ds)", call_sid, duration)
        except Exception:
            logger.exception("[entrypoint] failed to finalize CallLog")

    @ctx.room.on("disconnected")
    def on_disconnected():
        asyncio.create_task(_finalize_call_log())

    await session.start(agent=agent, room=ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
