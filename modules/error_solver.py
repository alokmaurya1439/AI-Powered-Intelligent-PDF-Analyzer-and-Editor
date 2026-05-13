"""
Error Solver Module — AI-powered text correction and layout-preserving PDF correction.
Handles small, medium, and large PDFs via parallel chunked LLM calls.
"""
import os
import re
import json
import shutil
import logging
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

import fitz
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
logging.basicConfig(level=logging.INFO)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

client: Optional[Groq] = None
if GROQ_API_KEY and GROQ_API_KEY != "your_groq_api_key_here":
    try:
        client = Groq(api_key=GROQ_API_KEY)
        logging.info("✅ Groq error solver client initialized")
    except Exception as e:
        logging.warning(f"Groq init failed: {e}")

_CHUNK_SIZE = 3000   # chars per LLM chunk
_MAX_WORKERS = 5     # parallel LLM threads

_UNICODE_MAP = {
    "\u201c": '"', "\u201d": '"',
    "\u2018": "'", "\u2019": "'",
    "\u2013": "-", "\u2014": "-",
    "\u2026": "...",
}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _clean_unicode(text: str) -> str:
    for uc, asc in _UNICODE_MAP.items():
        text = text.replace(uc, asc)
    return text


def split_text(text: str, chunk_size: int = _CHUNK_SIZE) -> List[str]:
    """Split on sentence boundaries to avoid cutting mid-sentence."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) + 1 <= chunk_size:
            current += s + " "
        else:
            if current:
                chunks.append(current.strip())
            if len(s) > chunk_size:
                for i in range(0, len(s), chunk_size):
                    chunks.append(s[i:i + chunk_size])
                current = ""
            else:
                current = s + " "
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text]


def _map_to_base14(raw_font: str) -> str:
    fn = raw_font.lower()
    bold = "bold" in fn
    italic = "italic" in fn or "oblique" in fn
    if "times" in fn or "roman" in fn:
        if bold and italic:
            return "Times-BoldItalic"
        if bold:
            return "Times-Bold"
        if italic:
            return "Times-Italic"
        return "Times-Roman"
    if "courier" in fn or "mono" in fn:
        if bold and italic:
            return "Courier-BoldOblique"
        if bold:
            return "Courier-Bold"
        if italic:
            return "Courier-Oblique"
        return "Courier"
    if bold and italic:
        return "Helvetica-BoldOblique"
    if bold:
        return "Helvetica-Bold"
    if italic:
        return "Helvetica-Oblique"
    return "Helvetica"


# ─────────────────────────────────────────────
# TEXT CORRECTION  (parallel chunks)
# ─────────────────────────────────────────────
def _correct_chunk(args) -> tuple:
    idx, chunk = args
    if client is None:
        return idx, chunk
    prompt = (
        "You are a professional editor.\n"
        "Correct grammar, spelling, punctuation, and awkward sentences.\n"
        "IMPORTANT: Keep structure similar. Do NOT add content. Return ONLY corrected text.\n\n"
        f"Text:\n{chunk}"
    )
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=2000,
        )
        content = resp.choices[0].message.content
        return idx, content.strip() if content else chunk
    except Exception as e:
        logging.error(f"correct_chunk {idx} error: {e}")
        return idx, chunk


def correct_text(text: str) -> str:
    """Correct full text using parallel LLM calls — fast for any size."""
    if not text.strip() or client is None:
        return text
    chunks = split_text(text)
    logging.info(f"correct_text: {len(chunks)} chunks")
    results = [""] * len(chunks)
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        for idx, corrected in ex.map(_correct_chunk, enumerate(chunks)):
            results[idx] = corrected
    return "\n".join(results)


# ─────────────────────────────────────────────
# CORRECTION MAP  (parallel chunks)
# ─────────────────────────────────────────────
def _correction_map_chunk(args) -> dict:
    idx, chunk = args
    if client is None:
        return {}
    prompt = (
        "You are a professional proofreader.\n"
        "Identify ONLY words/short phrases with errors (spelling, grammar, punctuation).\n"
        "Return a valid JSON object: {\"wrong\": \"correct\"}.\n"
        "Do NOT rewrite sentences. If no errors, return {}.\n\n"
        f"TEXT:\n{chunk}"
    )
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=800,
        )
        raw = resp.choices[0].message.content or "{}"
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        logging.warning(f"correction_map_chunk {idx} error: {e}")
    return {}


def _build_correction_map(text: str) -> dict:
    """Build full correction map for any size document — parallel chunks."""
    if client is None:
        return {}
    chunks = split_text(text, chunk_size=5000)
    logging.info(f"_build_correction_map: {len(chunks)} chunks")
    merged: dict = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        for result in ex.map(_correction_map_chunk, enumerate(chunks)):
            merged.update(result)
    return merged


# ─────────────────────────────────────────────
# LAYOUT-PRESERVING PDF CORRECTION
# ─────────────────────────────────────────────
def correct_pdf_layout_safe(
    file_path: str,
    layout_output: str = "corrected_layout.pdf",
    clean_output: str = "corrected_clean.pdf",
) -> dict:
    """
    Correct PDF IN-PLACE: same layout, fonts, sizes.
    Only erroneous words are redacted and reinserted at the exact same position.
    Works for small, medium, and large PDFs.
    """
    if not os.path.exists(file_path):
        return {"error": "File not found"}

    doc = fitz.open(file_path)
    try:
        # Try direct text extraction first
        full_text = "\n".join(p.get_text() for p in doc if p.get_text().strip())

        # Scanned PDF fallback — use OCR to get text for building correction map
        if not full_text.strip():
            logging.info("No direct text found — using OCR for correction map")
            doc.close()
            try:
                from modules.pdf_reader import extract_text_or_ocr
                full_text = extract_text_or_ocr(file_path)
            except Exception as ocr_err:
                logging.error(f"OCR fallback failed: {ocr_err}")
                full_text = ""
            # Re-open for editing
            doc = fitz.open(file_path)

        # If still no text at all, return original unchanged — nothing to correct
        if not full_text.strip():
            doc.close()
            shutil.copy(file_path, layout_output)
            shutil.copy(file_path, clean_output)
            return {"layout_pdf": layout_output, "clean_pdf": clean_output, "note": "No text found — original returned"}

        correction_map = _build_correction_map(full_text)
        logging.info(f"Correction map: {len(correction_map)} entries")

        # No errors found — PDF is already correct, return original as-is
        if not correction_map:
            doc.close()
            shutil.copy(file_path, layout_output)
            shutil.copy(file_path, clean_output)
            return {"layout_pdf": layout_output, "clean_pdf": clean_output, "note": "No errors found"}

        for page in doc:
            page_dict = page.get_text("dict")

            # Mark spans that need correction
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        span_text = span.get("text", "")
                        if not span_text.strip():
                            continue
                        new_text = span_text
                        for wrong, correct in correction_map.items():
                            if wrong in new_text:
                                new_text = new_text.replace(wrong, correct)
                        if new_text == span_text:
                            continue

                        page.add_redact_annot(fitz.Rect(span["bbox"]), fill=(1, 1, 1))
                        c = span.get("color", 0)
                        span["_new"] = new_text
                        span["_font"] = _map_to_base14(span.get("font", ""))
                        span["_size"] = span.get("size", 11)
                        span["_color"] = (
                            ((c >> 16) & 0xFF) / 255.0,
                            ((c >> 8) & 0xFF) / 255.0,
                            (c & 0xFF) / 255.0,
                        )

            page.apply_redactions()

            # Re-insert corrected text at original positions
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if "_new" not in span:
                            continue
                        pt = fitz.Point(span["bbox"][0], span["bbox"][1] + span["_size"] * 0.85)
                        for font in [span["_font"], "Helvetica"]:
                            try:
                                page.insert_text(pt, span["_new"], fontname=font,
                                                 fontsize=span["_size"], color=span["_color"])
                                break
                            except Exception as e:
                                logging.warning(f"insert_text({font}): {e}")

        doc.save(layout_output)
        doc.close()
        shutil.copy(layout_output, clean_output)
        return {"layout_pdf": layout_output, "clean_pdf": clean_output}

    except Exception as e:
        logging.error(f"correct_pdf_layout_safe error: {e}")
        try:
            doc.close()
        except Exception:
            pass
        # Fallback — return original file unchanged rather than failing
        try:
            shutil.copy(file_path, layout_output)
            shutil.copy(file_path, clean_output)
            return {"layout_pdf": layout_output, "clean_pdf": clean_output,
                     "note": f"Correction failed ({e}), original returned"}
        except Exception:
            return {"error": str(e)}


# ─────────────────────────────────────────────
# SCRIPT / FONT DETECTION
# ─────────────────────────────────────────────
def detect_script_type(text: str) -> str:
    if any('\u0900' <= c <= '\u097F' for c in text): return "devanagari"
    if any('\u0A80' <= c <= '\u0AFF' for c in text): return "gujarati"
    if any('\u0B80' <= c <= '\u0BFF' for c in text): return "tamil"
    if any('\u4E00' <= c <= '\u9FFF' for c in text): return "cjk"
    return "latin"


def _resolve_font_path(script_type: str) -> Optional[str]:
    candidates = {
        "devanagari": [r"C:\Windows\Fonts\Nirmala.ttf", r"C:\Windows\Fonts\mangal.ttf"],
        "gujarati":   [r"C:\Windows\Fonts\Nirmala.ttf", r"C:\Windows\Fonts\Shruti.ttf"],
        "tamil":      [r"C:\Windows\Fonts\Nirmala.ttf", r"C:\Windows\Fonts\Latha.ttf"],
        "cjk":        [r"C:\Windows\Fonts\msyh.ttc",    r"C:\Windows\Fonts\msgothic.ttc"],
        "latin":      [r"C:\Windows\Fonts\arial.ttf",   r"C:\Windows\Fonts\tahoma.ttf"],
    }
    for path in candidates.get(script_type, []) + candidates["latin"]:
        if os.path.exists(path):
            return path
    return None


# ─────────────────────────────────────────────
# PDF GENERATION  (fpdf2 — auto-paginates)
# ─────────────────────────────────────────────
def _generate_with_fpdf(text: str, output_path: str, script_type: str) -> Optional[str]:
    from fpdf import FPDF
    font_path = _resolve_font_path(script_type)
    pdf = FPDF(unit="pt", format="letter")
    pdf.set_auto_page_break(auto=True, margin=40)
    pdf.add_page()

    if font_path:
        try:
            pdf.add_font("UF", style="", fname=font_path)
            pdf.set_font("UF", size=11)
            try:
                pdf.set_text_shaping(True)
            except Exception:
                pass
        except Exception as fe:
            logging.warning(f"Custom font failed: {fe}")
            font_path = None
            pdf.set_font("Helvetica", size=11)
    else:
        pdf.set_font("Helvetica", size=11)

    for line in text.splitlines():
        if line.strip():
            clean = _clean_unicode(line)
            safe = clean if font_path else clean.encode("latin-1", "replace").decode("latin-1")
            try:
                pdf.multi_cell(0, 16, text=safe)
            except Exception:
                pdf.multi_cell(0, 16, text=safe.encode("ascii", "replace").decode("ascii"))
        else:
            pdf.ln(10)

    pdf.output(output_path)
    return output_path


def generate_corrected_pdf(corrected_text: str, output_path: str) -> Optional[str]:
    """
    Generate a Unicode-safe PDF.
    - Non-Latin scripts (Hindi, Gujarati, etc.): uses PyMuPDF with system font
    - Latin scripts: uses fpdf2
    """
    if not corrected_text or not corrected_text.strip():
        return None

    script_type = detect_script_type(corrected_text)

    # For non-Latin scripts, use PyMuPDF which handles Unicode natively
    if script_type != "latin":
        try:
            return _generate_with_pymupdf(corrected_text, output_path, script_type)
        except Exception as e:
            logging.warning(f"PyMuPDF generation failed for {script_type}: {e}")

    # Latin or fallback: use fpdf2
    try:
        return _generate_with_fpdf(corrected_text, output_path, script_type)
    except Exception as e:
        logging.error(f"generate_corrected_pdf error: {e}")
        # Last resort: PyMuPDF for Latin too
        try:
            return _generate_with_pymupdf(corrected_text, output_path, "latin")
        except Exception as e2:
            logging.error(f"All PDF generation failed: {e2}")
            return None


def _generate_with_pymupdf(text: str, output_path: str, script_type: str) -> Optional[str]:
    """Generate PDF using PyMuPDF — best Unicode support, no extra deps."""
    font_path = _resolve_font_path(script_type)

    doc = fitz.open()
    page_w, page_h = 612, 792
    margin = 50
    line_h = 18
    font_size = 11

    page = doc.new_page(width=page_w, height=page_h)
    y = margin

    for line in text.splitlines():
        if y + line_h > page_h - margin:
            page = doc.new_page(width=page_w, height=page_h)
            y = margin

        if line.strip():
            try:
                if font_path:
                    page.insert_text(
                        fitz.Point(margin, y),
                        line,
                        fontfile=font_path,
                        fontname="customfont",
                        fontsize=font_size,
                        color=(0, 0, 0),
                    )
                else:
                    page.insert_text(
                        fitz.Point(margin, y),
                        line,
                        fontsize=font_size,
                        color=(0, 0, 0),
                    )
            except Exception:
                # Strip to ASCII if font can't render
                try:
                    page.insert_text(
                        fitz.Point(margin, y),
                        line.encode("ascii", "replace").decode("ascii"),
                        fontsize=font_size,
                        color=(0, 0, 0),
                    )
                except Exception:
                    pass
        y += line_h

    doc.save(output_path)
    doc.close()
    return output_path


# ─────────────────────────────────────────────
# WRITING IMPROVEMENT  (parallel chunks)
# ─────────────────────────────────────────────
def _improve_chunk(args) -> tuple:
    idx, chunk, instruction = args
    if client is None:
        return idx, chunk
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a writing expert."},
                {"role": "user", "content": f"{instruction}\n\n{chunk}"},
            ],
            temperature=0.5,
            max_tokens=2000,
        )
        content = resp.choices[0].message.content
        return idx, content.strip() if content else chunk
    except Exception as e:
        logging.error(f"improve_chunk {idx} error: {e}")
        return idx, chunk


def improve_writing(text: str, improvement_type: str = "general") -> str:
    if client is None or not text.strip():
        return text
    instructions = {
        "clarity": "Rewrite for maximum clarity and readability.",
        "conciseness": "Make this text concise without losing meaning.",
        "engagement": "Make this text more engaging and compelling.",
        "general": "Improve the overall quality of this text.",
    }
    instruction = instructions.get(improvement_type, instructions["general"])
    chunks = split_text(text)
    results = [""] * len(chunks)
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        for idx, improved in ex.map(_improve_chunk, ((i, c, instruction) for i, c in enumerate(chunks))):
            results[idx] = improved
    return "\n".join(results)


# ─────────────────────────────────────────────
# FORMAT FIX — in-place, same layout as original
# ─────────────────────────────────────────────
def _fix_span_text(text: str) -> str:
    """Clean text: normalise quotes/dashes, collapse multiple spaces."""
    text = _clean_unicode(text)
    text = re.sub(r'[ \t]{2,}', ' ', text)  # multiple spaces → one
    return text.strip()


def _decode_color(color_int: int) -> tuple:
    """PyMuPDF integer colour → (r, g, b) floats 0–1."""
    return (
        ((color_int >> 16) & 0xFF) / 255.0,
        ((color_int >> 8) & 0xFF) / 255.0,
        ( color_int        & 0xFF) / 255.0,
    )


def fix_formatting_pdf_layout(file_path: str, output_path: str) -> Optional[str]:
    """
    Fix extra spaces IN-PLACE — output PDF looks IDENTICAL to the original.

    For every text span that contains extra whitespace:
      1. Redact (white-out) the original span bounding box.
      2. Re-insert the cleaned text at the EXACT same (x, y) position,
         with the EXACT same font name, font size, and colour.

    Spans that are already clean are left completely untouched.
    Images, graphics, page geometry — everything else is preserved exactly.
    """
    if not os.path.exists(file_path):
        logging.error(f"fix_formatting_pdf_layout: file not found: {file_path}")
        return None

    try:
        # Work on a copy so the original is never modified
        shutil.copy(file_path, output_path)
        doc = fitz.open(output_path)

        for page in doc:
            page_dict = page.get_text("dict")
            # Collect spans that need fixing
            spans_to_fix = []

            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:  # skip image blocks
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        raw = span.get("text", "")
                        if not raw.strip():
                            continue
                        fixed = _fix_span_text(raw)
                        if fixed == raw:
                            continue   # already clean — do not touch

                        x0, y0, x1, y1 = span["bbox"]
                        size      = span.get("size", 11)
                        color_int = span.get("color", 0)
                        font      = _map_to_base14(span.get("font", ""))
                        color     = _decode_color(color_int)

                        spans_to_fix.append({
                            "bbox":  fitz.Rect(x0, y0, x1, y1),
                            "text":  fixed,
                            "size":  size,
                            "font":  font,
                            "color": color,
                            # baseline: top-of-span + ~85 % of font size
                            "pt":    fitz.Point(x0, y0 + size * 0.85),
                        })

            if not spans_to_fix:
                continue   # page is already clean

            # Step 1: mark all dirty spans for redaction
            for s in spans_to_fix:
                page.add_redact_annot(s["bbox"], fill=(1, 1, 1))

            # Step 2: apply redactions (white-out)
            page.apply_redactions()

            # Step 3: re-insert cleaned text at original positions
            for s in spans_to_fix:
                for fn in [s["font"], "Helvetica"]:
                    try:
                        page.insert_text(
                            s["pt"], s["text"],
                            fontname=fn,
                            fontsize=s["size"],
                            color=s["color"],
                        )
                        break
                    except Exception as ins_err:
                        logging.warning(f"insert_text({fn}): {ins_err}")
                        try:
                            page.insert_text(
                                s["pt"],
                                s["text"].encode("ascii", "replace").decode("ascii"),
                                fontname="Helvetica",
                                fontsize=s["size"],
                                color=s["color"],
                            )
                            break
                        except Exception:
                            pass

        doc.save(output_path, incremental=False, encryption=fitz.PDF_ENCRYPT_NONE)
        doc.close()
        logging.info(f"fix_formatting_pdf_layout: saved → {output_path}")
        return output_path

    except Exception as e:
        logging.error(f"fix_formatting_pdf_layout error: {e}")
        try:
            shutil.copy(file_path, output_path)
            return output_path
        except Exception:
            return None


# ─────────────────────────────────────────────
# FORMAT FIX  (parallel chunks — text-only)
# ─────────────────────────────────────────────
def _format_chunk(args) -> tuple:
    idx, chunk, instruction = args
    if client is None:
        return idx, chunk
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a formatting expert."},
                {"role": "user", "content": f"{instruction}\n\n{chunk}"},
            ],
            temperature=0.2,
            max_tokens=2000,
        )
        content = resp.choices[0].message.content
        return idx, content.strip() if content else chunk
    except Exception as e:
        logging.error(f"format_chunk {idx} error: {e}")
        return idx, chunk


def fix_formatting(text: str, target_format: str = "standard") -> str:
    if client is None or not text.strip():
        return text
    instructions = {
        "academic": "Format this text in a clear academic style.",
        "business": "Format this text in a professional business style.",
        "standard": "Fix formatting: normalize spacing, indentation, and paragraph structure.",
    }
    instruction = instructions.get(target_format, instructions["standard"])
    chunks = split_text(text)
    results = [""] * len(chunks)
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        for idx, fixed in ex.map(_format_chunk, ((i, c, instruction) for i, c in enumerate(chunks))):
            results[idx] = fixed
    return "\n".join(results)
