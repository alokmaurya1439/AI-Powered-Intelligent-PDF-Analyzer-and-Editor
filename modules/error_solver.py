from groq import Groq
import os
import logging
from typing import List
import fitz  # PyMuPDF
from dotenv import load_dotenv
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ================= GROQ CLIENT =================
load_dotenv()
logging.basicConfig(level=logging.INFO)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

client = None
if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        logging.warning(f"Groq init failed: {e}")
        client = None


# ================= TEXT CHUNKING =================
def split_text(text: str, chunk_size: int = 1500) -> List[str]:
    """Split text into safe chunks for LLM."""
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


# ✅======= AI TEXT CORRECTION (WITH FALLBACK) =======
def correct_text(text):
    """Generate corrected text based on detected errors."""
    if not text.strip():
        return text

    if client is None:
        return text  # fallback: no correction

    chunks = split_text(text)
    corrected_chunks = []

    for chunk in chunks:
        prompt = f"""
        You are a professional editor.

        Correct the text while preserving original document structure.
        Grammar errors,
        Spelling mistakes,
        Punctuation mistakes,
        Awkward or unclear sentences,
        Semantic errors (wrong meaning) and clarify the meaning if needed

        IMPORTANT:
            - Keep sentence structure similar
            - Do NOT add extra content
            - Return only corrected text

        Text:
        {chunk}
        """
        try:
            response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": prompt}
            ],
            )

            content = response.choices[0].message.content
            corrected_chunks.append(content.strip() if content else chunk)

        except Exception as e:
            logging.error(f"LLM error: {e}")
            corrected_chunks.append(chunk)  # fallback

    return "\n".join(corrected_chunks)



# ================= SAFE PDF CORRECTION =================
def correct_pdf_layout_safe(
    file_path: str,
    layout_output: str = "corrected_layout.pdf",
    clean_output: str = "corrected_clean.pdf"
):
    """
    Safely correct PDF text while preserving layout.
    """

    if not os.path.exists(file_path):
        return {"error": "File not found"}

    doc = fitz.open(file_path)

    try:
        # ===== STEP 1: Extract text =====
        original_text = "\n".join(
            page.get_text()
            for page in doc
            if page.get_text().strip()
        )

        # ===== STEP 2: AI correction =====
        corrected_text = correct_text(original_text)

        # ===== STEP 3: LIGHT layout overlay (SAFE) =====
        for page in doc:
            rect = page.rect

            # Add corrected text overlay (instead of risky word replacement)
            page.insert_textbox(
                rect,
                corrected_text[:2000],  # limit overlay
                fontsize=10,
                color=(0, 0, 0),
            )

        doc.save(layout_output)

        # ===== STEP 4: Clean PDF =====
        generate_corrected_pdf(corrected_text, clean_output)

        return {
            "layout_pdf": layout_output,
            "clean_pdf": clean_output
        }

    except Exception as e:
        logging.error(f"PDF correction error: {e}")
        return {"error": str(e)}

    finally:
        doc.close()


# ================= LANGUAGE DETECTION =================
def detect_script_type(text: str) -> str:
    """Detect if text contains non-Latin characters."""
    # Check for common non-Latin scripts
    if any('\u0900' <= c <= '\u097F' for c in text):  # Devanagari (Hindi, Sanskrit)
        return "devanagari"
    if any('\u0A80' <= c <= '\u0AFF' for c in text):  # Gujarati
        return "gujarati"
    if any('\u0B80' <= c <= '\u0BFF' for c in text):  # Tamil
        return "tamil"
    if any('\u4E00' <= c <= '\u9FFF' for c in text):  # CJK (Chinese, Japanese, Korean)
        return "cjk"
    return "latin"


def _resolve_font_path(script_type: str) -> str | None:
    """Pick a Windows font that can render the requested script."""
    candidates = {
        "devanagari": [
            r"C:\Windows\Fonts\Nirmala.ttf",
            r"C:\Windows\Fonts\mangal.ttf",
        ],
        "gujarati": [
            r"C:\Windows\Fonts\Nirmala.ttf",
            r"C:\Windows\Fonts\Shruti.ttf",
        ],
        "tamil": [
            r"C:\Windows\Fonts\Nirmala.ttf",
            r"C:\Windows\Fonts\Latha.ttf",
        ],
        "cjk": [
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\msgothic.ttc",
        ],
        "latin": [
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\tahoma.ttf",
        ],
    }

    for path in candidates.get(script_type, []) + candidates["latin"]:
        if os.path.exists(path):
            return path
    return None


def _generate_with_fpdf(corrected_text: str, output_path: str, script_type: str) -> str | None:
    """Generate a Unicode-safe PDF using fpdf2."""
    from fpdf import FPDF

    font_path = _resolve_font_path(script_type)
    pdf = FPDF(unit="pt", format="letter")
    pdf.set_auto_page_break(auto=True, margin=40)
    pdf.add_page()

    if font_path:
        pdf.add_font("UnicodeFont", style="", fname=font_path)
        pdf.set_font("UnicodeFont", size=11)
        try:
            pdf.set_text_shaping(True)
        except Exception as exc:
            logging.warning(f"Text shaping not available: {exc}")
    else:
        pdf.set_font("Helvetica", size=11)

    for line in corrected_text.splitlines():
        if line.strip():
            safe_line = line if font_path else line.encode("latin-1", "replace").decode("latin-1")
            pdf.multi_cell(0, 16, text=safe_line)
        else:
            pdf.ln(10)

    pdf.output(output_path)
    return output_path


# ================= CLEAN PDF =================
def generate_corrected_pdf(corrected_text: str, output_path: str):
    """Generate clean corrected PDF with proper Unicode support using PyMuPDF."""
    try:
        script_type = detect_script_type(corrected_text)
        if script_type != "latin":
            return _generate_with_fpdf(corrected_text, output_path, script_type)

        doc = fitz.open()
        page = doc.new_page()

        font_path = _resolve_font_path("latin")
        margin = 50
        rect = fitz.Rect(margin, margin, page.rect.width - margin, page.rect.height - margin)
        
        if font_path:
            page.insert_font(fontname="F0", fontfile=font_path)
            page.insert_textbox(
                rect,
                corrected_text,
                fontsize=11,
                fontname="F0",
                color=(0, 0, 0)
            )
        else:
            # Fallback to standard PDF font if no Unicode font is found
            page.insert_textbox(
                rect,
                corrected_text,
                fontsize=11,
                fontname="helv",
                color=(0, 0, 0)
            )
        
        doc.save(output_path)
        doc.close()
        return output_path
        
    except Exception as e:
        logging.error(f"PDF generation error in generate_corrected_pdf: {e}")
        try:
            return _generate_with_fpdf(corrected_text, output_path, detect_script_type(corrected_text))
        except Exception as fallback_error:
            logging.error(f"Fallback PDF generation failed: {fallback_error}")
            return None


# ================= WRITING IMPROVEMENT =================
def improve_writing(text: str, improvement_type: str = "general") -> str:
    """Improve writing quality."""

    if client is None:
        return text

    improvements = {
        "clarity": "Make clearer",
        "conciseness": "Make concise",
        "engagement": "Make engaging",
        "general": "Improve overall quality"
    }

    instruction = improvements.get(improvement_type, improvements["general"])

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a writing expert."},
                {"role": "user", "content": f"{instruction}\n\n{text}"}
            ],
            temperature=0.5
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logging.error(f"Improve error: {e}")
        return text


# ================= FORMAT FIX =================
def fix_formatting(text: str, target_format: str = "standard") -> str:
    """Fix formatting issues."""

    if client is None:
        return text

    formats = {
        "academic": "Format academically",
        "business": "Format professionally",
        "standard": "Improve readability"
    }

    instruction = formats.get(target_format, formats["standard"])

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a formatting expert."},
                {"role": "user", "content": f"{instruction}\n\n{text}"}
            ],
            temperature=0.2
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logging.error(f"Format error: {e}")
        return text
