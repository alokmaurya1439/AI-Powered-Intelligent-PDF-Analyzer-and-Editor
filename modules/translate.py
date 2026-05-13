"""
translate.py — AI-powered PDF Translation Module
=================================================
• Auto language detection via Groq AI
• Context-aware, meaning-based translation (not word-for-word)
• Preserves sentence meaning, tone, and document structure
• Parallel page processing for speed
• Primary model: llama-3.3-70b-versatile | Fallback: llama-3.1-8b-instant
• Automatic retry + rate-limit backoff
"""

import os
import re
import time
import json
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

# ── Configuration ──────────────────────────────────────────────────────────────
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "").strip()
MODEL_PRIMARY  = "llama-3.3-70b-versatile"
MODEL_FALLBACK = "llama-3.1-8b-instant"
_MAX_WORKERS   = int(os.getenv("TRANSLATE_BLOCK_WORKERS", "5"))
_GROQ_TIMEOUT  = float(os.getenv("GROQ_TRANSLATE_TIMEOUT", "45"))

# ── Initialize Groq client ─────────────────────────────────────────────────────
_groq_client = None
if GROQ_API_KEY and GROQ_API_KEY not in {"", "your_groq_api_key_here"}:
    try:
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY)
        logging.info("✅ Groq translate client initialized")
    except Exception as _e:
        logging.warning(f"⚠️ Groq client init failed: {_e}")
else:
    logging.warning("⚠️ GROQ_API_KEY not set — translation will be unavailable")

# ── Supported language names (code → full name) ────────────────────────────────
LANG_NAMES = {
    "en": "English",   "hi": "Hindi",      "gu": "Gujarati",
    "fr": "French",    "es": "Spanish",     "de": "German",
    "ar": "Arabic",    "zh": "Chinese (Simplified)", "ja": "Japanese",
    "pt": "Portuguese","ru": "Russian",     "it": "Italian",
    "ko": "Korean",    "tr": "Turkish",     "nl": "Dutch",
    "pl": "Polish",    "sv": "Swedish",     "da": "Danish",
    "fi": "Finnish",   "no": "Norwegian",   "cs": "Czech",
    "sk": "Slovak",    "ro": "Romanian",    "hu": "Hungarian",
    "uk": "Ukrainian", "sr": "Serbian",     "hr": "Croatian",
    "sl": "Slovenian", "he": "Hebrew",      "fa": "Persian",
    "bn": "Bengali",   "pa": "Punjabi",     "mr": "Marathi",
    "ta": "Tamil",     "te": "Telugu",      "th": "Thai",
    "vi": "Vietnamese","id": "Indonesian",  "ms": "Malay",
    "sw": "Swahili",   "ur": "Urdu",        "el": "Greek",
    "zh-tw": "Chinese (Traditional)",
}

# ── Auto-detect sentinel values ────────────────────────────────────────────────
_AUTO_DETECT_VALUES = {"auto", "auto detect", "auto-detect", "detect", ""}


# ==============================================================================
# Internal helpers
# ==============================================================================

def _resolve_lang(lang: str) -> str:
    """Convert language code or name to full display name."""
    if not lang:
        return "Hindi"
    lower = lang.strip().lower()
    if lower in LANG_NAMES:
        return LANG_NAMES[lower]
    return lang.strip().title()


def _is_auto_lang(lang: Optional[str]) -> bool:
    """Return True if the lang value means 'auto detect'."""
    return not lang or lang.strip().lower() in _AUTO_DETECT_VALUES


def _clean(text: str) -> str:
    """Strip model preamble / code fences from translated output."""
    if not text:
        return text
    # Remove code fences
    text = re.sub(r"```[^\n]*\n?", "", text).replace("```", "")
    # Remove common label prefixes the model sometimes adds
    for label in [
        "Translation:", "Translated text:", "Translated:", "Output:",
        "Here is the translation:", "Here's the translation:",
        "Translating:", "Result:",
    ]:
        if text.strip().lower().startswith(label.lower()):
            text = text.strip()[len(label):].strip()
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_json_array(raw: str) -> list:
    """Parse a model response that should be a JSON array."""
    if not raw:
        raise ValueError("Empty JSON response")
    cleaned = re.sub(r"```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    cleaned = cleaned.replace("```", "").strip()
    try:
        parsed = json.loads(cleaned)
    except Exception:
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON array found in: {cleaned[:200]}")
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON array")
    return parsed


def _normalise_item(item, original: str) -> str:
    """Accept either a plain string or a dict with a 'translation' key."""
    if isinstance(item, str):
        text = item
    elif isinstance(item, dict):
        text = (
            item.get("translation")
            or item.get("translated")
            or item.get("translated_text")
            or item.get("output")
            or item.get("text")
            or original
        )
    else:
        text = original
    return _clean(str(text).strip()) if str(text).strip() else original


# ==============================================================================
# Core single-block translation
# ==============================================================================

def _call_groq_single(
    text: str,
    target_lang: str,
    model: str,
    source_lang: Optional[str] = None,
) -> str:
    """Single Groq call for one text block. Raises on failure."""
    source = (
        "the detected source language"
        if _is_auto_lang(source_lang)
        else _resolve_lang(source_lang)
    )
    resp = _groq_client.chat.completions.create(
        model=model,
        temperature=0.05,
        max_tokens=4096,
        timeout=_GROQ_TIMEOUT,
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are a professional document translator. "
                    f"Translate from {source} into {target_lang}.\n"
                    "STRICT RULES:\n"
                    "1. Output ONLY the translated text — no labels, no commentary.\n"
                    "2. Preserve line breaks and paragraph structure exactly.\n"
                    "3. Keep names, numbers, dates, emails, URLs, codes unchanged.\n"
                    "4. Do NOT add explanations, headings, or markdown.\n"
                    "5. Translate meaning — not word-for-word literally."
                ),
            },
            {"role": "user", "content": text},
        ],
    )
    content = resp.choices[0].message.content
    if not content or not content.strip():
        raise ValueError("Empty response from model")
    return content


def _translate_one(
    text: str,
    target_lang: str,
    source_lang: Optional[str] = None,
) -> str:
    """
    Translate one text block with retry + model fallback.
    Returns original text if all attempts fail.
    """
    if not text or not text.strip():
        return text

    for model in [MODEL_PRIMARY, MODEL_FALLBACK]:
        for attempt in range(2):
            try:
                result = _call_groq_single(text, target_lang, model, source_lang)
                return _clean(result)
            except Exception as e:
                err = str(e)
                if "429" in err or "rate_limit" in err.lower():
                    # Parse retry-after if provided
                    m = re.search(r"try again in (\d+)m(\d+)", err)
                    wait = (int(m.group(1)) * 60 + int(m.group(2))) if m else 8
                    wait = min(wait, 20)
                    logging.warning(f"Rate limit on {model}, waiting {wait}s…")
                    if attempt == 0:
                        time.sleep(wait)
                    break  # move to fallback model
                else:
                    logging.warning(f"translate error ({model}, attempt {attempt+1}): {e}")
                    if attempt == 0:
                        time.sleep(1)

    logging.error("All translation attempts failed — returning original text")
    return text


# ==============================================================================
# Batch / page-context translation
# ==============================================================================

def _call_groq_blocks(
    texts: List[str],
    target_lang: str,
    model: str,
    source_lang: Optional[str] = None,
    prefer_fast: bool = False,
) -> List[str]:
    """
    Translate a list of text blocks in a single Groq call.
    Sends all blocks as a JSON array so the model has full page context.
    Returns a list of translations in the same order.
    """
    source = (
        "auto-detected source language"
        if _is_auto_lang(source_lang)
        else _resolve_lang(source_lang)
    )
    payload = [{"id": i, "source_text": t} for i, t in enumerate(texts)]

    resp = _groq_client.chat.completions.create(
        model=model,
        temperature=0.02,
        max_tokens=4096 if prefer_fast else 8192,
        timeout=_GROQ_TIMEOUT,
        messages=[
            {
                "role": "system",
                "content": (
                    f"You translate PDF page text from {source} into {target_lang}.\n"
                    "Return ONLY valid JSON — no markdown, no extra text.\n"
                    'Return exactly this shape: [{"id": 0, "translation": "..."}, ...]\n'
                    "Array length, ids, and order MUST match the input exactly.\n"
                    "Translate each block naturally using the full page context.\n"
                    "Keep names, numbers, dates, URLs, emails, and codes unchanged.\n"
                    "Translate meaning — not word-for-word. Do NOT add any labels."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ],
    )

    raw = resp.choices[0].message.content or ""
    parsed = _extract_json_array(raw)

    if len(parsed) != len(texts):
        raise ValueError(
            f"Expected {len(texts)} translations, got {len(parsed)}"
        )

    # Build result — prefer id-keyed lookup for stability
    by_id: dict = {}
    ordered: list = []
    for idx, item in enumerate(parsed):
        translated = _normalise_item(item, texts[idx])
        ordered.append(translated)
        if isinstance(item, dict):
            try:
                by_id[int(item["id"])] = translated
            except Exception:
                pass

    result = (
        [by_id.get(i, texts[i]) for i in range(len(texts))]
        if len(by_id) == len(texts)
        else ordered
    )

    # Guard against the model echoing the input unchanged
    if result == texts:
        raise ValueError("Model echoed input without translating")

    return result


# ==============================================================================
# Public API
# ==============================================================================

def translate_blocks_parallel(
    texts: List[str],
    target_lang: str,
    source_lang: Optional[str] = None,
) -> List[str]:
    """
    Translate a list of text strings in parallel (one API call per block).
    Each string is one PDF paragraph/block. Results are in the same order.
    Use this when blocks are independent (no shared context needed).
    """
    if not texts or _groq_client is None:
        return texts

    target = _resolve_lang(target_lang)
    source = None if _is_auto_lang(source_lang) else _resolve_lang(source_lang)
    if source and source.lower() == target.lower():
        return texts

    results = [""] * len(texts)
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(texts))) as pool:
        future_map = {
            pool.submit(_translate_one, t, target, source): i
            for i, t in enumerate(texts)
        }
        for fut in as_completed(future_map):
            idx = future_map[fut]
            try:
                results[idx] = fut.result()
            except Exception as e:
                logging.error(f"Block {idx} failed: {e}")
                results[idx] = texts[idx]

    return results


def translate_blocks_contextual(
    texts: List[str],
    target_lang: str,
    source_lang: Optional[str] = None,
    prefer_fast: bool = False,
) -> List[str]:
    """
    Translate all text blocks from one PDF page in a SINGLE Groq call.
    This gives the model full page context for better meaning-based translation.
    Falls back to parallel per-block translation if the batch call fails.

    Args:
        texts:        List of text strings (one per PDF block on a page).
        target_lang:  Target language name or code (e.g. "Hindi", "hi").
        source_lang:  Source language name/code, or None for auto-detect.
        prefer_fast:  If True, uses the smaller/faster fallback model.

    Returns:
        List of translated strings in the same order as input.
    """
    if not texts:
        return texts
    if _groq_client is None:
        raise ValueError("GROQ_API_KEY is not configured. Please add your Groq API key to the .env file to enable translation.")

    target = _resolve_lang(target_lang)
    source = None if _is_auto_lang(source_lang) else _resolve_lang(source_lang)
    if source and source.lower() == target.lower():
        return texts

    models = [MODEL_FALLBACK] if prefer_fast else [MODEL_PRIMARY, MODEL_FALLBACK]
    attempts = 1 if prefer_fast else 2

    for model in models:
        for attempt in range(attempts):
            try:
                return _call_groq_blocks(texts, target, model, source_lang, prefer_fast)
            except Exception as e:
                logging.warning(
                    f"Contextual translate failed ({model}, attempt {attempt+1}): {e}"
                )
                if attempt + 1 < attempts:
                    time.sleep(1)

    if prefer_fast:
        raise ValueError("Translation failed using Fast mode. Please try 'High Quality' mode or check your API key/rate limits.")

    logging.warning("Context translation failed — falling back to per-block parallel translation")
    parallel_result = translate_blocks_parallel(texts, target, source)
    
    if parallel_result == texts:
        raise ValueError("Translation failed (model returned original text). Please check your API rate limits or try a different language.")
        
    return parallel_result


def detect_language(text: str) -> dict:
    """
    Detect the primary language of a given text using Groq AI.

    Args:
        text: Sample text from the document (first 800 chars is sufficient).

    Returns:
        dict with keys: language_name, language_code, confidence
        e.g. {"language_name": "Hindi", "language_code": "hi", "confidence": "high"}
    """
    _default = {"language_name": "Unknown", "language_code": "auto", "confidence": "low"}

    if not text or not text.strip():
        return _default

    if _groq_client is None:
        logging.warning("detect_language: Groq client not available")
        return _default

    sample = text[:800].strip()
    prompt = (
        "Identify the primary language of this text.\n"
        "Respond ONLY with a JSON object in this exact format — no markdown:\n"
        '{"language_name": "English", "language_code": "en", "confidence": "high"}\n\n'
        "confidence must be one of: high, medium, low\n\n"
        f"Text:\n{sample}"
    )

    for model in [MODEL_PRIMARY, MODEL_FALLBACK]:
        try:
            resp = _groq_client.chat.completions.create(
                model=model,
                temperature=0.01,
                max_tokens=80,
                timeout=_GROQ_TIMEOUT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = (resp.choices[0].message.content or "").strip()
            raw = re.sub(r"```[^\n]*\n?", "", raw).replace("```", "").strip()
            parsed = json.loads(raw)
            return {
                "language_name": parsed.get("language_name", "Unknown"),
                "language_code": parsed.get("language_code", "auto"),
                "confidence":    parsed.get("confidence", "medium"),
            }
        except Exception as ex:
            logging.warning(f"detect_language ({model}): {ex}")

    return _default


async def translate_text(
    text: str,
    target_lang: str = "Hindi",
    source_lang: Optional[str] = None,
) -> str:
    """
    Async wrapper — translate arbitrary-length text.
    Splits into paragraphs and translates in parallel.

    Args:
        text:        Full document text to translate.
        target_lang: Target language name or code.
        source_lang: Source language name/code, or None for auto-detect.

    Returns:
        Translated text as a single string.
    """
    if not isinstance(text, str) or not text.strip():
        return "⚠️ No valid text provided."

    if _groq_client is None:
        return (
            "⚠️ Translation unavailable: GROQ_API_KEY is not configured.\n\n"
            + text
        )

    target = _resolve_lang(target_lang)
    # Split into paragraphs for parallel translation
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if not paras:
        paras = [text]

    loop = asyncio.get_event_loop()
    translated = await loop.run_in_executor(
        None, translate_blocks_parallel, paras, target, source_lang
    )
    return "\n\n".join(translated)


async def translate_single_block(text: str, target_lang: str) -> str:
    """Async wrapper — translate a single text block."""
    if not isinstance(text, str) or not text.strip():
        return text
    if _groq_client is None:
        return text
    target = _resolve_lang(target_lang)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _translate_one, text.strip(), target, None)


async def translate_text_block(
    text: str,
    target_lang: str = "Hindi",
    source_lang: Optional[str] = None,
) -> str:
    """Alias for translate_single_block (backward compat)."""
    return await translate_single_block(text, target_lang)


# ── Backward-compatibility alias ───────────────────────────────────────────────
def translate_lines_batch(lines: List[str], target_lang: str) -> List[str]:
    """Translate a list of lines (backward-compat wrapper)."""
    return translate_blocks_parallel(lines, target_lang)
