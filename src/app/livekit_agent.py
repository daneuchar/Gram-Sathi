"""LiveKit Agents entrypoint for Gram Saathi."""
from __future__ import annotations

import asyncio
import json
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
_MARKDOWN_RE = re.compile(r'\*{1,2}([^*]+)\*{1,2}')  # **bold** or *italic* → text


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


def _is_tool_call_json(text: str) -> bool:
    """Detect if text is a tool call JSON that LiveKit sends through the TTS pipeline."""
    stripped = text.strip()
    if not stripped.startswith("{") or not stripped.endswith("}"):
        return False
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict) and "name" in parsed and (
            "call_id" in parsed or "arguments" in parsed or "parameters" in parsed
        ):
            return True
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return False


_TTS_REPLACEMENTS = {
    "मंडी": "मण्डी",
    "₹": "रुपये ",
}


def _clean_for_tts(text: str) -> str:
    """Remove markdown formatting and fix TTS pronunciation issues."""
    text = _MARKDOWN_RE.sub(r'\1', text)  # **bold** / *italic* → text
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)  # # headers
    text = re.sub(r'[`~]{3,}.*', '', text)  # code fences
    text = text.replace('`', '')  # inline code
    text = re.sub(r'\n{2,}', '. ', text)  # double newlines → period
    text = text.replace('\n', ' ')  # single newlines → space
    for wrong, right in _TTS_REPLACEMENTS.items():
        text = text.replace(wrong, right)
    return text.strip()


async def _strip_markers(
    text: AsyncIterable[str], stt_plugin: sarvam.STT, tts_plugin: sarvam.TTS
) -> AsyncIterable[str]:
    """Strip <<<...>>> markers, <thinking> blocks, and tool call JSON from LLM output stream."""
    buf = ""
    async for chunk in text:
        buf += chunk

        # Skip tool call JSON entirely — LiveKit sends FunctionToolCall as text through TTS
        if _is_tool_call_json(buf):
            logger.debug("[tts_node] stripping tool call JSON: %s", buf[:120])
            buf = ""
            continue

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
            to_speak = _clean_for_tts(buf[:hold_idx])
            if to_speak:
                logger.debug("[tts_node] yielding to TTS: %s", to_speak[:150])
                yield to_speak
        buf = buf[hold_idx:]

    # Final cleanup of any remaining markers/thinking in buffer
    buf = _THINKING_RE.sub("", buf)
    buf = _MARKER_RE.sub("", buf).strip()
    # Final check for tool call JSON in remaining buffer
    if buf and _is_tool_call_json(buf):
        logger.debug("[tts_node] stripping final tool call JSON: %s", buf[:120])
        buf = ""
    buf = _clean_for_tts(buf)
    if buf:
        logger.debug("[tts_node] yielding final to TTS: %s", buf[:150])
        yield buf


def build_system_prompt(profile: dict | None) -> str:
    """Return main system prompt with profile context, or onboarding prompt."""
    if profile is None:
        return ONBOARDING_PROMPT
    today = datetime.now().strftime("%B %d, %Y")
    name = profile.get("name", "")
    state = profile.get("state", "")
    district = profile.get("district", "")
    crops = profile.get("crops", "")
    land_acres = profile.get("land_acres")
    lang = profile.get("language", "en-IN")
    lang_map = {
        "hi-IN": "Hindi", "ta-IN": "Tamil", "te-IN": "Telugu",
        "kn-IN": "Kannada", "mr-IN": "Marathi", "bn-IN": "Bengali",
        "gu-IN": "Gujarati", "pa-IN": "Punjabi", "ml-IN": "Malayalam",
        "od-IN": "Odia", "en-IN": "English",
    }
    lang_name = lang_map.get(lang, "English")

    # Language-specific filler/respectful words to override Hindi defaults in the prompt
    lang_fillers = {
        "hi-IN": "'जी', 'हाँ', 'अच्छा', 'जी हाँ', 'बताती हूँ'",
        "ta-IN": "'சரி', 'ஆமா', 'சொல்றேன்', 'கொஞ்சம் பொறுங்க'",
        "te-IN": "'అవునండి', 'చెప్తాను', 'సరే', 'అలాగే'",
        "kn-IN": "'ಹೌದು', 'ಸರಿ', 'ಹೇಳ್ತೀನಿ', 'ಆಯ್ತು'",
        "mr-IN": "'हो', 'बरोबर', 'सांगते', 'हो ना'",
        "bn-IN": "'হ্যাঁ', 'বলছি', 'ঠিক আছে', 'আচ্ছা'",
        "gu-IN": "'હા', 'સારું', 'કહું છું', 'ઠીક છે'",
        "pa-IN": "'ਹਾਂ ਜੀ', 'ਦੱਸਦੀ ਹਾਂ', 'ਠੀਕ ਹੈ', 'ਅੱਛਾ'",
        "ml-IN": "'ശരി', 'പറയാം', 'അതെ', 'ഒന്ന് കാത്തിരിക്കൂ'",
        "od-IN": "'ହଁ', 'କହୁଛି', 'ଠିକ୍ ଅଛି', 'ଆଚ୍ଛା'",
        "en-IN": "'yes', 'sure', 'let me check', 'of course'",
    }
    fillers = lang_fillers.get(lang, lang_fillers["en-IN"])

    # Language-specific number formatting examples (words only, no digits)
    lang_number_examples = {
        "hi-IN": "say 'दो हज़ार रुपये क्विंटल' NOT '2000 रुपये'. Example: 'टमाटर का भाव अभी दो हज़ार रुपये क्विंटल चल रहा है, जी हाँ, दो हज़ार रुपये।'",
        "ta-IN": "say 'இரண்டாயிரம் ரூபாய் குவிண்டால்' NOT '2000 ரூபாய்'. Example: 'தக்காளி விலை இப்போ இரண்டாயிரம் ரூபாய் குவிண்டால், ஆமா, இரண்டாயிரம் ரூபாய்.'",
        "te-IN": "say 'రెండు వేల రూపాయలు క్వింటాల్' NOT '2000 రూపాయలు'. Example: 'టమాటా ధర ఇప్పుడు రెండు వేల రూపాయలు క్వింటాల్, అవునండి, రెండు వేలు.'",
        "kn-IN": "say 'ಎರಡು ಸಾವಿರ ರೂಪಾಯಿ ಕ್ವಿಂಟಾಲ್' NOT '2000 ರೂಪಾಯಿ'. Example: 'ಟೊಮ್ಯಾಟೊ ಬೆಲೆ ಈಗ ಎರಡು ಸಾವಿರ ರೂಪಾಯಿ ಕ್ವಿಂಟಾಲ್.'",
        "mr-IN": "say 'दोन हजार रुपये क्विंटल' NOT '2000 रुपये'. Example: 'टोमॅटोचा भाव आत्ता दोन हजार रुपये क्विंटल आहे, हो, दोन हजार रुपये.'",
        "bn-IN": "say 'দুই হাজার টাকা কুইন্টাল' NOT '2000 টাকা'. Example: 'টমেটোর দাম এখন দুই হাজার টাকা কুইন্টাল, হ্যাঁ, দুই হাজার টাকা।'",
        "gu-IN": "say 'બે હજાર રૂપિયા ક્વિન્ટલ' NOT '2000 રૂપિયા'. Example: 'ટામેટાનો ભાવ અત્યારે બે હજાર રૂપિયા ક્વિન્ટલ છે, હા, બે હજાર રૂપિયા.'",
        "pa-IN": "say 'ਦੋ ਹਜ਼ਾਰ ਰੁਪਏ ਕੁਇੰਟਲ' NOT '2000 ਰੁਪਏ'. Example: 'ਟਮਾਟਰ ਦਾ ਭਾਅ ਹੁਣ ਦੋ ਹਜ਼ਾਰ ਰੁਪਏ ਕੁਇੰਟਲ ਹੈ, ਹਾਂ ਜੀ, ਦੋ ਹਜ਼ਾਰ ਰੁਪਏ.'",
        "ml-IN": "say 'രണ്ടായിരം രൂപ ക്വിന്റൽ' NOT '2000 രൂപ'. Example: 'തക്കാളിയുടെ വില ഇപ്പോൾ രണ്ടായിരം രൂപ ക്വിന്റൽ ആണ്, അതെ, രണ്ടായിരം രൂപ.'",
        "od-IN": "say 'ଦୁଇ ହଜାର ଟଙ୍କା କୁଇଣ୍ଟାଲ' NOT '2000 ଟଙ୍କା'. Example: 'ଟମାଟୋ ଦାମ ଏବେ ଦୁଇ ହଜାର ଟଙ୍କା କୁଇଣ୍ଟାଲ, ହଁ, ଦୁଇ ହଜାର ଟଙ୍କା।'",
        "en-IN": "say 'two thousand rupees per quintal' NOT '2000 rupees'. Example: 'Tomato price is two thousand rupees per quintal right now, yes, two thousand rupees.'",
    }
    number_example = lang_number_examples.get(lang, lang_number_examples["en-IN"])

    profile_ctx = (
        f"Today's date: {today}. "
        f"Farmer profile — Name: {name}, State: {state}, District: {district}, "
        f"Crops: {crops or 'unknown'}, Land: {land_acres or 'unknown'} acres, Language: {lang_name}. "
        f"CRITICAL: You MUST respond ONLY in {lang_name}. Every word you say must be in {lang_name}. "
        f"Do NOT use Hindi unless the farmer's language IS Hindi. "
        f"Greet them by name ONLY on the very first turn. After that, do NOT use their name in every response. "
        f"Mix it up naturally — sometimes just answer directly, sometimes use respectful words like {fillers}. "
        f"Use their name only occasionally, like real phone conversations. "
        f"When the farmer asks about prices, weather, etc. WITHOUT specifying a location, default to {state}, {district}. "
        f"But if they mention ANY other state, city, or district, use THAT location — do not restrict to {state}. "
        f"When checking scheme eligibility, use the farmer's profile data directly — do NOT ask the farmer for information you already have (state, crops, land size). "
        f"Number formatting: {number_example}"
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
    # Normalize phone: ensure it starts with +
    phone = phone.strip()
    if phone and not phone.startswith("+"):
        phone = "+" + phone
    logger.info("[entrypoint] resolved phone=%s", phone)
    user = await get_or_create_user(phone) if phone else None
    profile = {"name": user.name, "state": user.state, "district": user.district, "language": user.language, "crops": user.crops, "land_acres": user.land_acres} if user and user.name else None
    language = (profile.get("language") or "en-IN") if profile else "en-IN"
    is_onboarding = profile is None

    # STT: Sarvam streaming
    stt_plugin = sarvam.STT(
        model="saaras:v3",
        language=language,
        api_key=settings.sarvam_api_key,
    )

    # TTS: Sarvam bulbul with female voice (8kHz for SIP/phone calls)
    tts_plugin = sarvam.TTS(
        model="bulbul:v3",
        target_language_code=language,
        speaker="ishita",
        api_key=settings.sarvam_api_key,
        max_chunk_length=500,
        pace=1.1,
        speech_sample_rate=8000,
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

    # ── Pre-cache weather & mandi data ──
    async def _precache():
        # Always prefetch demo locations
        demo_locations = [
            ("Karnal", "Haryana"),
            ("Hyderabad", "Telangana"),
        ]
        demo_crops = [
            ("wheat", "Haryana"),
            ("rice", "Haryana"),
            ("tomato", "Haryana"),
            ("onion", "Haryana"),
            ("mustard", "Haryana"),
            ("potato", "Haryana"),
            ("tomato", "Telangana"),
            ("rice", "Telangana"),
            ("onion", "Telangana"),
            ("cotton", "Telangana"),
            ("chilli", "Telangana"),
            ("eggplant", "Telangana"),
        ]
        # Add user-specific data if returning user
        if profile and not is_onboarding:
            state = profile.get("state", "")
            district = profile.get("district", "")
            if district and state and (district, state) not in demo_locations:
                demo_locations.append((district, state))
            crops_str = (user.crops or "") if user else ""
            for crop in [c.strip() for c in crops_str.split(",") if c.strip()]:
                if (crop, state) not in demo_crops:
                    demo_crops.append((crop, state))
        try:
            for district, state in demo_locations:
                await asyncio.to_thread(_get_weather, district, state)
                logger.info("[precache] weather cached for %s, %s", district, state)
            for crop, state in demo_crops:
                await asyncio.to_thread(_get_mandi, crop, state, None)
                logger.info("[precache] mandi cached for %s in %s", crop, state)
        except Exception:
            logger.debug("[precache] pre-cache failed (non-critical)", exc_info=True)
    asyncio.create_task(_precache())

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
    user_has_spoken = False

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
        nonlocal is_onboarding, user_has_spoken
        item = event.item

        # Save user and assistant message turns
        if isinstance(item, ChatMessage) and item.role in ("user", "assistant"):
            text = item.content[0] if isinstance(item.content, list) and item.content else ""
            text = str(text)

            if item.role == "user" and text.strip():
                user_has_spoken = True

            if text:
                await _save_turn(item.role, text)

            # Check for END_CALL marker — auto-disconnect after farewell
            # ONLY if the farmer has actually spoken at least once
            if item.role == "assistant" and "<<<END_CALL>>>" in text and not user_has_spoken:
                logger.warning("[end_call] ignoring END_CALL in greeting — farmer hasn't spoken yet")
            elif item.role == "assistant" and "<<<END_CALL>>>" in text:
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
                    land_acres = profile_data.get("land_acres")
                    if land_acres is not None:
                        try:
                            land_acres = float(land_acres)
                        except (ValueError, TypeError):
                            land_acres = None
                    await update_user_profile(
                        phone,
                        name=profile_data.get("name"),
                        state=profile_data.get("state"),
                        district=profile_data.get("district"),
                        language=profile_data.get("language"),
                        crops=profile_data.get("crops"),
                        land_acres=land_acres,
                    )
                    logger.info("[onboarding] profile saved for %s: %s", phone, profile_data)

                    # Update CallLog language now that we know it
                    detected_lang = profile_data.get("language", "en-IN")
                    try:
                        async with AsyncSessionLocal() as db:
                            log = await db.get(CallLog, call_sid)
                            if log:
                                log.language_detected = detected_lang
                                await db.commit()
                        logger.info("[onboarding] updated CallLog language to %s", detected_lang)
                    except Exception:
                        logger.exception("[onboarding] failed to update CallLog language")

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

    # For SIP callbacks, the agent joins the room BEFORE the farmer is dialed.
    # Delay session.start() until the farmer connects, so the STT stream
    # doesn't waste its ~70s Sarvam timeout waiting for the farmer to pick up.
    is_sip_callback = ctx.room.name.startswith("gram-saathi-callback-")
    if is_sip_callback:
        # Check if a non-agent participant is already connected
        farmer_already_here = any(
            p.kind != rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
            for p in ctx.room.remote_participants.values()
        )
        if not farmer_already_here:
            farmer_connected = asyncio.Event()

            @ctx.room.on("participant_connected")
            def _on_farmer_connected(participant):
                logger.info("[sip-callback] farmer connected: %s", participant.identity)
                farmer_connected.set()

            logger.info("[sip-callback] waiting for farmer to connect before starting session...")
            try:
                await asyncio.wait_for(farmer_connected.wait(), timeout=60)
            except (TimeoutError, asyncio.TimeoutError):
                logger.warning("[sip-callback] farmer never connected, aborting")
                return
        else:
            logger.info("[sip-callback] farmer already in room, starting immediately")

    await session.start(agent=agent, room=ctx.room)

    # Proactive greeting — agent speaks first without waiting for farmer
    session.generate_reply()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
