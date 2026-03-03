import asyncio
import io
import logging
import wave
from collections.abc import AsyncGenerator

import numpy as np
from fastrtc import ReplyOnPause

from app.database import get_or_create_user, update_user_profile
from app.models.user import User
from app.pipeline.nova_client import ONBOARDING_PROMPT, extract_profile_marker
from app.pipeline.pipeline import process_turn_streaming

logger = logging.getLogger(__name__)

SAMPLE_RATE = 8000


def _ndarray_to_wav(sample_rate: int, audio: np.ndarray) -> bytes:
    """Convert a numpy int16 array to WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


async def _safe_process_turn_streaming(
    audio_bytes: bytes,
    farmer_profile,
    conversation_history: list[dict],
    language_code: str,
    audio_queue: asyncio.Queue,
    sample_rate: int,
    system_prompt: str | None = None,
) -> tuple[str, str, str]:
    """Wrapper that guarantees None sentinel is put even if pipeline raises."""
    try:
        return await process_turn_streaming(
            audio_bytes=audio_bytes,
            farmer_profile=farmer_profile,
            conversation_history=conversation_history,
            language_code=language_code,
            audio_queue=audio_queue,
            sample_rate=sample_rate,
            system_prompt=system_prompt,
        )
    except Exception:
        logger.exception("process_turn_streaming error")
        await audio_queue.put(None)
        return ("", language_code, "")


class GramSaathiHandler(ReplyOnPause):
    """Voice handler for Gram Saathi.

    ReplyOnPause runs Silero VAD on each incoming audio frame and calls
    _reply_fn only once per complete utterance (after a pause is detected).
    _reply_fn is an async generator that yields (sample_rate, ndarray) audio
    chunks back to the caller as they become available.
    """

    def __init__(self):
        super().__init__(
            fn=self._reply_fn,
            output_sample_rate=SAMPLE_RATE,
            can_interrupt=False,
        )
        self.conversation_history: list[dict] = []
        self.language_code = "hi-IN"
        self.phone: str | None = None
        self.is_onboarding: bool = False
        self.farmer_profile: dict | None = None
        self._profile_loaded: bool = False

    def copy(self) -> "GramSaathiHandler":
        """Called by FastRTC for each new WebRTC/Twilio connection."""
        return GramSaathiHandler()

    def _is_new_user(self, user: User) -> bool:
        return user.name is None

    async def _ensure_profile_loaded(self, phone: str) -> None:
        """Load or create user on first turn. Sets is_onboarding + farmer_profile."""
        if self._profile_loaded:
            return
        self.phone = phone
        user = await get_or_create_user(phone)
        self._profile_loaded = True  # only set after successful DB lookup
        if self._is_new_user(user):
            self.is_onboarding = True
            self.farmer_profile = None
            logger.info("[ONBOARD] New user %s — starting onboarding", phone)
        else:
            self.is_onboarding = False
            self.farmer_profile = {
                "phone": user.phone,
                "name": user.name,
                "state": user.state,
                "district": user.district,
                "language": user.language,
            }
            if user.language:
                self.language_code = user.language
            logger.info("[PROFILE] Returning user %s — %s", phone, user.name)

    async def _reply_fn(self, audio: tuple[int, np.ndarray], webrtc_id: str = "", phone: str = "") -> AsyncGenerator:
        """Called once per full utterance (after Silero VAD detects a pause).

        FastRTC passes (audio, webrtc_id, *additional_inputs) — webrtc_id is the
        connection ID string injected by FastRTC before the Gradio additional_inputs.
        phone is passed from the Gradio phone number text box via additional_inputs.
        """
        # Load profile from DB on first turn
        if phone:
            await self._ensure_profile_loaded(phone)

        sample_rate, arr = audio
        wav_bytes = _ndarray_to_wav(sample_rate, arr.reshape(-1))

        system_prompt = ONBOARDING_PROMPT if self.is_onboarding else None

        audio_queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(
            _safe_process_turn_streaming(
                audio_bytes=wav_bytes,
                farmer_profile=self.farmer_profile,
                conversation_history=list(self.conversation_history[-20:]),
                language_code=self.language_code,
                audio_queue=audio_queue,
                sample_rate=SAMPLE_RATE,
                system_prompt=system_prompt,
            )
        )

        # Drain audio queue, yielding each chunk to FastRTC as it arrives
        while True:
            item = await audio_queue.get()
            if item is None:
                break
            yield item

        transcript, detected_lang, english_response = await task

        # Check for PROFILE marker when onboarding
        if self.is_onboarding and english_response:
            profile_data, english_response = extract_profile_marker(english_response)
            if profile_data:
                await update_user_profile(
                    self.phone,
                    name=profile_data.get("name"),
                    state=profile_data.get("state"),
                    district=profile_data.get("district"),
                    language=detected_lang,
                )
                self.farmer_profile = {
                    "phone": self.phone,
                    "name": profile_data.get("name"),
                    "state": profile_data.get("state"),
                    "district": profile_data.get("district"),
                    "language": detected_lang,
                }
                self.is_onboarding = False
                logger.info("[ONBOARD] Profile saved for %s: %s", self.phone, profile_data)

        if transcript:
            self.conversation_history.append(
                {"role": "user", "content": [{"text": transcript}]}
            )
            if english_response:
                self.conversation_history.append(
                    {"role": "assistant", "content": [{"text": english_response}]}
                )
            self.language_code = detected_lang
            logger.info("[%s] user: %s", detected_lang, transcript)
            logger.info("[%s] assistant: %s", detected_lang, english_response)
