from groq import Groq
import os
import logging
from typing import Dict
from pypdf import PdfReader
from dotenv import load_dotenv

from modules.blank_detector import find_blank_in_file

load_dotenv()
logging.basicConfig(level=logging.INFO)

GROQ_API_KEY= os.getenv("GROQ_API_KEY", "").strip()

# Initialize Groq client safely
client = None
if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        logging.warning("⚠️ GROQ API client initialization failed:", e)
        client = None


# ================= BASIC FALLBACK =================
def _basic_error_analysis(text: str) -> str:
    """Fallback heuristic analyzer when LLM is unavailable."""
    if not text.strip():
        return "⚠ No text to evaluate."

    issues = []
    lowered = text.lower()

    # Simple heuristics
    if "  " in text:
        issues.append("Extra whitespace detected")

    if any(x in lowered for x in [" a error", " an error", "ing errors"]):
        issues.append("Possible grammatical issue detected")

    if text.count(",") > text.count(".") * 3:
        issues.append("Possible punctuation imbalance")

    if not issues:
        return "✅ No obvious grammar or spelling issues detected (basic check)."

    return "\n".join(f"• {issue}" for issue in issues)



# ================= LLM ERROR DETECTION =================
def detect_errors(text: str) -> str:
    """
    Detect grammar, spelling, and semantic errors using LLM (with fallback).
    """

    if not isinstance(text, str) or not text.strip():
        return "⚠ No valid text provided"

    # Limit size (LLM token safety)
    text = text[:2000]

    # Fallback if API unavailable
    if client is None:
        return _basic_error_analysis(text)

    prompt = f"""
    You are a professional document editor.

    Analyze the text and identify:

    1. Grammar errors
    2. Spelling mistakes
    3. Punctuation issues
    4. Awkward sentences
    5. Semantic mistakes

    Return structured output:

    Error:
    Correction:
    Explanation:

    TEXT:
    {text}
    """

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=512,
        )

        content = (
            response.choices[0].message.content
            if response and response.choices
            else None
        )

        if content:
            return content.strip()

        return _basic_error_analysis(text)

    except Exception as e:
        logging.error(f"❌ Groq API error: {e}")
        return _basic_error_analysis(text)


# ================= BLANK FIELD DETECTION =================
find_blank_fields = find_blank_in_file


# ================= PDF ISSUE DETECTION =================
def detect_pdf_issues(file_path: str) -> Dict:
    """
    Detect structural issues in PDF.
    """

    if not file_path or not os.path.exists(file_path):
        return {"error": "Invalid file path"}

    issues = {}

    try:
        reader = PdfReader(file_path)

        # Encryption
        if reader.is_encrypted:
            issues["encryption"] = "PDF is encrypted"

        # Empty PDF
        if len(reader.pages) == 0:
            issues["empty"] = "PDF has no pages"

        # Text presence check
        has_text = False
        for page in reader.pages[:5]:
            try:
                txt = page.extract_text() or ""
                if txt.strip():
                    has_text = True
                    break
            except:
                continue

        if not has_text:
            issues["no_text"] = "Likely scanned PDF (no selectable text)"

        return issues if issues else {"status": "No major issues detected"}

    except Exception as e:
        return {"error": f"PDF analysis failed: {str(e)}"}


# ================= TEXT QUALITY =================
def check_text_quality(text: str) -> Dict:
    """
    Analyze text quality metrics.
    """

    if not isinstance(text, str) or not text.strip():
        return {"error": "Text must be non-empty"}

    words = text.split()

    quality = {
        "word_count": len(words),
        "character_count": len(text),
        "sentence_count": text.count(".") + text.count("!") + text.count("?"),
        "avg_word_length": round(sum(len(w) for w in words) / max(len(words), 1), 2),
    }

    # Warnings
    if quality["word_count"] < 10:
        quality["warning"] = "Text is too short"
    elif quality["word_count"] > 10000:
        quality["warning"] = "Text is very long"

    if quality["sentence_count"] == 0:
        quality["note"] = "No clear sentence boundaries detected"

    return quality