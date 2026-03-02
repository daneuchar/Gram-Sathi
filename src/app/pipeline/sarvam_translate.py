import httpx
import logging

from app.config import settings

logger = logging.getLogger(__name__)

TRANSLATE_URL = "https://api.sarvam.ai/translate"

# Languages that don't need translation (English variants)
ENGLISH_LANGS = {"en-IN", "en-US", "en-GB", "en"}


async def translate(text: str, source_lang: str, target_lang: str) -> str:
    """Translate text between languages using Sarvam sarvam-translate:v1.

    Returns original text unchanged if source == target or both are English.
    """
    if not text.strip():
        return text

    # No translation needed for English ↔ English
    src_is_english = source_lang in ENGLISH_LANGS
    tgt_is_english = target_lang in ENGLISH_LANGS
    if src_is_english and tgt_is_english:
        return text
    if source_lang == target_lang:
        return text

    headers = {
        "api-subscription-key": settings.sarvam_api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "input": text,
        "source_language_code": source_lang,
        "target_language_code": target_lang,
        "model": "sarvam-translate:v1",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(TRANSLATE_URL, headers=headers, json=payload)
        resp.raise_for_status()

    return resp.json().get("translated_text", text)


async def to_english(text: str, source_lang: str) -> str:
    """Translate any Indian language text to English."""
    return await translate(text, source_lang, "en-IN")


async def from_english(text: str, target_lang: str) -> str:
    """Translate English text to an Indian language."""
    return await translate(text, "en-IN", target_lang)
