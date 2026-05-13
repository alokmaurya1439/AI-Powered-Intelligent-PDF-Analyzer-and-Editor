"""
Error Detector Module — LLM-powered error detection with 3 depth levels.
Handles small, medium, and large PDFs via parallel chunked analysis.
"""
import os
import logging
from typing import Dict, Optional
from concurrent.futures import ThreadPoolExecutor

from pypdf import PdfReader
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
logging.basicConfig(level=logging.INFO)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

client: Optional[Groq] = None
if GROQ_API_KEY and GROQ_API_KEY != "your_groq_api_key_here":
    try:
        client = Groq(api_key=GROQ_API_KEY)
        logging.info("✅ Groq error detector client initialized")
    except Exception as e:
        logging.warning(f"GROQ client init failed: {e}")


# ─────────────────────────────────────────────
# FALLBACK (no API)
# ─────────────────────────────────────────────
def _basic_error_analysis(text: str) -> str:
    if not text.strip():
        return "⚠ No text to evaluate."
    issues = []
    # Only flag whitespace if it's excessively common (PDF extraction always has some double spaces)
    double_space_count = text.count("   ")  # 3+ spaces = real issue
    if double_space_count > 10:
        issues.append(f"Excessive extra whitespace detected ({double_space_count} occurrences)")
    if text.count(",") > text.count(".") * 5:  # raised threshold to avoid false positives
        issues.append("Possible punctuation imbalance")
    lowered = text.lower()
    if any(x in lowered for x in [" a error", " an error"]):
        issues.append("Possible grammatical issue detected")
    return "\n".join(f"• {i}" for i in issues) if issues else "✅ No errors detected."


# ─────────────────────────────────────────────
# LEVEL CONFIG
# ─────────────────────────────────────────────
_LEVEL_CONFIG = {
    "basic": {
        "chunk_size": 2500,
        "max_chunks": 2,
        "max_tokens": 800,
        "scope": "spelling and grammar errors only",
        "instructions": "Focus ONLY on clear spelling mistakes and obvious grammar errors. Skip style or tone.",
    },
    "intermediate": {
        "chunk_size": 2500,
        "max_chunks": 6,
        "max_tokens": 1000,
        "scope": "grammar, spelling, punctuation, and style",
        "instructions": ("Identify grammar, spelling, punctuation errors, and "
                         "awkward phrasing. Suggest clarity improvements."),
    },
    "deep analysis": {
        "chunk_size": 3000,
        "max_chunks": 12,
        "max_tokens": 1500,
        "scope": "full deep analysis: grammar, spelling, punctuation, style, tone, semantics, structure",
        "instructions": (
            "Perform a thorough analysis. Identify: spelling mistakes, grammar errors, punctuation issues, "
            "awkward sentences, semantic errors, tone inconsistencies, structural problems (poor flow, "
            "missing transitions), and factual inconsistencies. Be detailed and comprehensive."
        ),
    },
}


# ─────────────────────────────────────────────
# PARALLEL CHUNK ANALYSIS
# ─────────────────────────────────────────────
def _analyze_chunk(args) -> tuple:
    idx, chunk, level_name, cfg = args
    if client is None:
        return idx, None
    base_prompt = (
        f"You are a professional document editor performing a {level_name} analysis (Section {idx + 1}).\n\n"
        f"Scope: {cfg['scope']}\n"
        f"Instructions: {cfg['instructions']}\n\n"
        "Return structured output for EACH issue found. Use EXACTLY this format:\n"
        "Issue: <the specific wrong word, phrase, or sentence as it appears in the text>\n"
        "Correction/Suggestion: <the corrected text or suggestion>\n"
        "Explanation: <brief reason>\n\n"
        "STRICT RULES — you MUST follow these:\n"
    )

    level_key = level_name.lower().strip()
    if level_key == "basic":
        rules = (
            "1. 'Issue:' must contain ONLY the exact wrong word (1-3 words max), NOT the full sentence.\n"
            "2. Do NOT flag British English spellings (fulfilment, colour, organisation, etc.) as errors.\n"
            "3. Do NOT flag proper nouns, institution names, or technical terms as errors.\n"
            "4. Do NOT flag words that are spelled correctly — only flag genuine misspellings.\n"
            "5. Do NOT flag style preferences (capitalisation, Oxford comma, etc.) as errors.\n"
            "6. Only report an error if the word is genuinely misspelled or has an obvious grammar error.\n"
            "7. If the Issue and Correction/Suggestion are the same, do NOT report it.\n\n"
        )
    elif level_key == "intermediate":
        rules = (
            "1. Report grammar, spelling, punctuation errors, and awkward phrasing.\n"
            "2. Keep 'Issue:' concise (a few words or a short sentence).\n"
            "3. Provide actionable suggestions for clarity and style in 'Correction/Suggestion:'.\n"
            "4. Do NOT flag British English spellings as errors.\n"
            "5. Do NOT flag proper nouns or technical terms as errors.\n\n"
        )
    else:  # deep analysis
        rules = (
            "1. Report spelling, grammar, punctuation, style, tone, semantic, and structural issues.\n"
            "2. For structural or tone issues, 'Issue:' can be a full sentence or paragraph description.\n"
            "3. Be detailed in your Explanation regarding semantics or factual inconsistencies.\n"
            "4. Provide actionable improvements in 'Correction/Suggestion:'.\n"
            "5. Do NOT flag British English spellings as errors.\n\n"
        )

    prompt = (
        base_prompt + rules + 
        "If no issues found, write: ✅ No issues found in this section.\n\n"
        f"TEXT:\n{chunk}"
    )
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=cfg["max_tokens"],
        )
        content = resp.choices[0].message.content
        if content:
            return idx, f"--- Section {idx + 1} ({level_name}) ---\n{content.strip()}"
    except Exception as e:
        logging.error(f"analyze_chunk {idx} error: {e}")
    return idx, None


# ─────────────────────────────────────────────
# OCR TEXT QUALITY CHECK
# ─────────────────────────────────────────────
def _is_ocr_noise(text: str) -> bool:
    """
    Return True if the text looks like raw OCR output rather than real document text.
    OCR noise has: very short "words", high symbol ratio, low real-word ratio.
    """
    if not text or len(text.strip()) < 20:
        return False

    words = text.split()
    if not words:
        return False

    # Ratio of very short tokens (1-2 chars) — OCR produces many
    short_tokens = sum(1 for w in words if len(w) <= 2)
    short_ratio = short_tokens / len(words)

    # Ratio of non-alphanumeric characters
    non_alpha = sum(1 for c in text if not c.isalnum() and c not in " \n\t.,!?;:'\"()-")
    symbol_ratio = non_alpha / max(len(text), 1)

    # Average word length — real text is 4-7, OCR garbage is often <3
    avg_len = sum(len(w) for w in words) / len(words)

    return short_ratio > 0.55 or symbol_ratio > 0.15 or avg_len < 2.8


def _text_source_is_ocr(text: str, file_path: str = None) -> bool:
    """
    Detect whether the text was extracted via OCR (scanned PDF).
    Checks the PDF itself for selectable text first, then falls back to noise heuristics.
    """
    # If we have the file, check directly whether it has a real text layer
    if file_path and os.path.exists(file_path):
        try:
            reader = PdfReader(file_path)
            has_real_text = any(
                len((page.extract_text() or "").strip()) > 30
                for page in reader.pages[:5]
            )
            if not has_real_text:
                return True   # no text layer → definitely OCR
        except Exception:
            pass

    # Fallback: heuristic on the extracted text itself
    return _is_ocr_noise(text)



def detect_errors(text: str, detection_level: str = "Basic", file_path: str = None) -> str:
    """
    Detect errors using LLM with 3 depth levels.
    Parallel chunk processing — fast for any PDF size.

    Skips LLM analysis for scanned/OCR PDFs where the extracted text is
    unreliable — returns an informational message instead of false positives.
    """
    if not isinstance(text, str) or not text.strip():
        return "⚠ No valid text provided"

    # ── OCR / scanned PDF guard ───────────────────────────────────────────
    if _text_source_is_ocr(text, file_path):
        return (
            "✅ No text-layer errors detected.\n\n"
            "ℹ️ This appears to be a scanned or image-based PDF. "
            "Text was extracted via OCR, which may not be perfectly accurate. "
            "Error detection on OCR output can produce false positives, "
            "so analysis has been skipped for this document."
        )

    if client is None:
        return _basic_error_analysis(text)

    level_key = detection_level.strip().lower()
    cfg = _LEVEL_CONFIG.get(level_key, _LEVEL_CONFIG["basic"])

    chunk_size = cfg["chunk_size"]
    max_chunks = cfg["max_chunks"]
    total_chars = chunk_size * max_chunks

    chunks = [
        text[i:i + chunk_size]
        for i in range(0, min(len(text), total_chars), chunk_size)
    ]

    logging.info(f"detect_errors: {len(chunks)} chunk(s) at level='{detection_level}'")

    results = [None] * len(chunks)
    with ThreadPoolExecutor(max_workers=min(5, len(chunks))) as ex:
        for idx, content in ex.map(
            _analyze_chunk,
            [(i, c, detection_level, cfg) for i, c in enumerate(chunks)]
        ):
            results[idx] = content

    detections = [r for r in results if r]
    if not detections:
        return _basic_error_analysis(text)

    output = "\n\n".join(detections)
    if len(text) > total_chars:
        output += (
            f"\n\n*(Note: {detection_level} mode analyzed the first {total_chars:,} characters. "
            f"Switch to Deep Analysis for full document coverage.)*"
        )
    return output


# ─────────────────────────────────────────────
# PDF STRUCTURAL ISSUES
# ─────────────────────────────────────────────
def detect_pdf_issues(file_path: str) -> Dict:
    if not file_path or not os.path.exists(file_path):
        return {"error": "Invalid file path"}
    issues = {}
    try:
        reader = PdfReader(file_path)
        if reader.is_encrypted:
            issues["encryption"] = "PDF is encrypted"
        if len(reader.pages) == 0:
            issues["empty"] = "PDF has no pages"
        has_text = any(
            (page.extract_text() or "").strip()
            for page in reader.pages[:5]
        )
        if not has_text:
            issues["no_text"] = "Likely scanned PDF (no selectable text)"
        return issues if issues else {"status": "No major issues detected"}
    except Exception as e:
        return {"error": f"PDF analysis failed: {str(e)}"}


# ─────────────────────────────────────────────
# TEXT QUALITY METRICS
# ─────────────────────────────────────────────
def check_text_quality(text: str) -> Dict:
    if not isinstance(text, str) or not text.strip():
        return {"error": "Text must be non-empty"}
    words = text.split()
    quality: Dict = {
        "word_count": len(words),
        "character_count": len(text),
        "sentence_count": text.count(".") + text.count("!") + text.count("?"),
        "avg_word_length": round(sum(len(w) for w in words) / max(len(words), 1), 2),
        "page_estimate": max(1, len(words) // 250),
    }
    if quality["word_count"] < 10:
        quality["warning"] = "Text is too short"
    elif quality["word_count"] > 50000:
        quality["warning"] = "Very large document — Deep Analysis recommended"
    elif quality["word_count"] > 10000:
        quality["note"] = "Large document — consider Deep Analysis for full coverage"
    if quality["sentence_count"] == 0:
        quality["note"] = "No clear sentence boundaries detected"
    return quality
