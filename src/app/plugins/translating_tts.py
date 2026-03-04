"""Translating TTS wrapper — translates English text before passing to inner TTS."""
from __future__ import annotations

import logging

from livekit.agents import tts

from app.plugins.sarvam_tts_wrapper import prepare_tts_text

logger = logging.getLogger(__name__)


class TranslatingTTS(tts.TTS):
    """Wraps a LiveKit TTS plugin, translating English text to the farmer's language."""

    def __init__(self, *, inner_tts: tts.TTS, language: str = "en-IN") -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=inner_tts.sample_rate,
            num_channels=inner_tts.num_channels,
        )
        self._inner = inner_tts
        self.language = language

    def synthesize(self, text: str, *, conn_options=None) -> tts.ChunkedStream:
        # synchronous path — translation must happen before this call
        # Use synthesize_translated() for the async path with translation
        return self._inner.synthesize(text)

    async def synthesize_translated(self, text: str) -> tts.ChunkedStream:
        """Translate text then synthesize with the inner TTS."""
        translated = await prepare_tts_text(text, self.language)
        logger.info("[TTS] %s → %s (%s)", text[:60], translated[:60], self.language)
        return self._inner.synthesize(translated)
