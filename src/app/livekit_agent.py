"""LiveKit Agents entrypoint for Gram Saathi."""
from __future__ import annotations

import logging

from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli
from livekit.plugins import sarvam, silero

from app.config import settings
from app.database import get_or_create_user, update_user_profile
from app.pipeline.nova_client import (
    ONBOARDING_PROMPT,
    SYSTEM_PROMPT,
    extract_profile_marker,
    extract_lang_marker,
)
from app.plugins.bedrock_llm import BedrockLLM
from app.plugins.translating_tts import TranslatingTTS

logger = logging.getLogger(__name__)


def build_system_prompt(profile: dict | None) -> str:
    """Return main system prompt with profile context, or onboarding prompt."""
    if profile is None:
        return ONBOARDING_PROMPT
    name = profile.get("name", "")
    state = profile.get("state", "")
    district = profile.get("district", "")
    profile_ctx = (
        f"Farmer profile — Name: {name}, State: {state}, District: {district}. "
        f"Greet them warmly by name on the first turn. "
        f"Default weather and mandi queries to {state}, {district}."
    )
    return SYSTEM_PROMPT + "\n\n" + profile_ctx


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    # Resolve farmer profile from phone number (passed in room metadata by SIP gateway)
    phone = ctx.room.metadata or ""
    user = await get_or_create_user(phone) if phone else None
    profile = {"name": user.name, "state": user.state, "district": user.district, "language": user.language} if user and user.name else None
    language = (profile.get("language") or "en-IN") if profile else "en-IN"

    # STT: Sarvam saaras:v3 streaming (built-in LiveKit plugin)
    stt_plugin = sarvam.STT(
        model="saaras:v2",
        language_code=language if profile else None,  # None = auto-detect during onboarding
        api_key=settings.sarvam_api_key,
    )

    # TTS: Sarvam bulbul wrapped with translation
    inner_tts = sarvam.TTS(
        model="bulbul:v2",
        target_language_code=language,
        api_key=settings.sarvam_api_key,
    )
    translating_tts = TranslatingTTS(inner_tts=inner_tts, language=language)

    agent = Agent(
        instructions=build_system_prompt(profile),
        stt=stt_plugin,
        llm=BedrockLLM(),
        tts=translating_tts,
        vad=silero.VAD.load(),
    )

    session = AgentSession()

    # Handle PROFILE marker from onboarding — save to DB and update session
    @session.on("conversation_item_added")
    async def on_item_added(event):
        item = event.item
        if item.role != "assistant":
            return
        text = item.content[0] if isinstance(item.content, list) and item.content else ""
        text = str(text)

        # Check for language marker
        lang_code, _ = extract_lang_marker(text)
        if lang_code:
            translating_tts.language = lang_code
            logger.info("[onboarding] language detected: %s", lang_code)

        # Check for profile marker
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

    await session.start(agent, room=ctx.room)
    await session.wait_for_close()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
