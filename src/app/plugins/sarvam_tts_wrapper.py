"""Pre-processing utilities for Sarvam TTS — markdown strip, number expansion, translation."""
from __future__ import annotations

import re

from app.pipeline.sarvam_translate import from_english, ENGLISH_LANGS

_MARKDOWN_RE = re.compile(r'[*_`#~>]+')
_MARKER_RE = re.compile(r'<<<[^>]*>>>')
_NUMBER_RE = re.compile(r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b|\b\d+(?:\.\d+)?\b')


def _strip_markdown(text: str) -> str:
    text = _MARKER_RE.sub('', text)
    text = _MARKDOWN_RE.sub('', text)
    return text.strip()


def _expand_numbers(text: str) -> str:
    from num2words import num2words

    def _replace(m: re.Match) -> str:
        raw = m.group().replace(",", "")
        try:
            n = float(raw)
            return num2words(int(n) if n == int(n) else n, lang="en")
        except Exception:
            return m.group()

    return _NUMBER_RE.sub(_replace, text)


async def prepare_tts_text(text: str, language_code: str) -> str:
    """Strip markdown, expand numbers, translate to farmer's language if needed."""
    text = _strip_markdown(text)
    text = _expand_numbers(text)
    if language_code not in ENGLISH_LANGS:
        text = await from_english(text, language_code)
    return text
