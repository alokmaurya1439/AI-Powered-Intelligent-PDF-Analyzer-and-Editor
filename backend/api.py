import uuid
import re
import fitz
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response, FileResponse
from starlette.background import BackgroundTask
import os
import shutil
import json
import logging
import base64
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# ========== Importing modules ==============
from modules.pdf_reader import extract_text_or_ocr, get_pdf_metadata
from modules.error_detector import detect_errors, detect_pdf_issues, check_text_quality
from modules.error_solver import correct_text, correct_pdf_layout_safe, generate_corrected_pdf
from modules.error_solver import improve_writing as improve_text_logic
from modules.error_solver import fix_formatting as fix_format_logic
from modules.error_solver import fix_formatting_pdf_layout
from modules.summarizer import summarize_text, extract_key_points
from modules.translate import (
    translate_text,
    translate_single_block,
    translate_lines_batch,
    translate_blocks_parallel,
    translate_blocks_contextual,
)
from modules.file_converter import FileConverter
from modules.pdf_editor import (
    add_text_replacement, add_image_to_pdf, merge_pdfs,
    split_pdf, add_watermark, add_header_footer,
    draw_shape, highlight_text,
    add_annotation, compress_pdf, add_bookmark,
    get_pdf_info, delete_pages, extract_pages,
    reorder_pages, rotate_pages, set_pdf_security,
    add_page_numbers, set_background_color, create_form_fields,
    add_blank_page,
)
from modules.blank_detector import find_blanks

# ========== Load env ===========
load_dotenv()
router = APIRouter()

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ================= COMMON UTILS =================
def save_file(file: UploadFile, extension: str = ""):
    """Save uploaded file to temp directory"""
    try:
        filename = f"{uuid.uuid4().hex}{extension}"
        file_path = f"{UPLOAD_DIR}/{filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return file_path
    except Exception as e:
        print("❌ File Save Error:", e)
        raise HTTPException(status_code=400, detail=f"File save failed: {str(e)}")


def cleanup_file(file_path: str):
    """Remove temporary file"""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        print(f"Cleanup warning: {e}")


def return_pdf_file(pdf_path: str, filename: str = "output.pdf"):
    """Read and return PDF as response, utilizing BackgroundTask to auto-delete after sending."""
    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(status_code=500, detail="PDF generation failed")
    
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=filename,
        background=BackgroundTask(cleanup_file, pdf_path)
    )


# ================= HEALTH CHECK =================
@router.get("/health")
async def health_check():
    """Check if API is running"""
    return {"status": "✅ API is running"}


# ================= MAIN PROCESS ===============
@router.post("/process")
async def process_pdf(file: UploadFile = File(...)):
    """Process PDF: Extract text, correct errors, regenerate PDF"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_processed.pdf"

    try:
        # Extract text
        try:
            text = extract_text_or_ocr(file_path)
        except Exception as e:
            print("❌ OCR Error:", e)
            text = ""
        
        # Correct text
        try:
            corrected = correct_text(text)
        except Exception as e:
            print("❌ AI Error:", e)
            corrected = text

        # Generate PDF
        pdf_file = generate_corrected_pdf(corrected, output_path)

        if not pdf_file or not os.path.exists(pdf_file):
            raise HTTPException(status_code=500, detail="PDF generation failed")

        return return_pdf_file(pdf_file, "processed.pdf")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= ERROR DETECTION ============
@router.post("/error-detector")
async def error_detector(
    file: UploadFile = File(...),
    detection_level: str = Form("Basic"),
    max_pages: int = Form(0)
):
    """Detect errors, issues, and quality in PDF"""
    file_path = save_file(file, ".pdf")

    try:
        text = extract_text_or_ocr(file_path, max_pages=max_pages if max_pages > 0 else None)
        metadata = get_pdf_metadata(file_path)

        errors = detect_errors(text, detection_level=detection_level, file_path=file_path)
        issues = detect_pdf_issues(file_path)
        quality = check_text_quality(text)

        return {
            "status": "success",
            "text": text,
            "metadata": metadata,
            "quality": quality,
            "issues": issues,
            "errors": errors,
            "text_length": len(text),
            "detection_level": detection_level
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= CORRECTED PDF =================
@router.post("/corrected-pdf")
async def corrected_pdf(file: UploadFile = File(...)):
    """Generate corrected PDF with error fixes"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_corrected.pdf"
    clean_output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_clean_corrected.pdf"
    
    try:
        result = correct_pdf_layout_safe(file_path, output_path, clean_output_path)

        # If error AND no fallback file was produced, raise
        if isinstance(result, dict) and result.get("error") and not result.get("clean_pdf"):
            raise HTTPException(status_code=500, detail=result["error"])

        pdf_file = result.get("clean_pdf") if isinstance(result, dict) else None

        if not pdf_file or not os.path.exists(pdf_file):
            raise HTTPException(status_code=500, detail="Correction failed and no fallback available")

        return return_pdf_file(pdf_file, "corrected.pdf")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= REPLACE TEXT =================
@router.post("/replace-text")
async def replace_text(
    file: UploadFile = File(...),
    old_text: str = Form(...),
    new_text: str = Form(...),
    font_name: str = Form(None),
    font_size: float = Form(None),
    color_r: float = Form(None),
    color_g: float = Form(None),
    color_b: float = Form(None),
    page_num: int = Form(-1)  # -1 = all pages, 0+ = specific page
):
    """Replace specific text in PDF with optional styling overrides"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_replaced.pdf"

    try:
        color = None
        if color_r is not None and color_g is not None and color_b is not None:
            color = (color_r, color_g, color_b)

        target_page = page_num if page_num >= 0 else None

        success = add_text_replacement(
            file_path,
            output_path,
            {old_text: new_text},
            font_name=font_name,
            font_size=font_size,
            color=color,
            page_num=target_page
        )

        if success:
            return return_pdf_file(output_path, "replaced.pdf")
        else:
            raise HTTPException(status_code=500, detail="Text replacement failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= VISUAL EDITING ENDPOINTS =================
@router.post("/get-page-blocks")
async def get_page_blocks_api(file: UploadFile = File(...), page_num: int = Form(...)):
    """Extract all text blocks for interactive editing"""
    file_path = save_file(file, ".pdf")
    try:
        from modules.pdf_editor import get_page_text_blocks
        return {"blocks": get_page_text_blocks(file_path, page_num)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)

@router.post("/get-page-image")
async def get_page_image_api(file: UploadFile = File(...), page_num: int = Form(...)):
    """Render a PDF page to image for visual preview"""
    file_path = save_file(file, ".pdf")
    try:
        from modules.pdf_editor import get_page_image
        img_bytes = get_page_image(file_path, page_num)
        if img_bytes:
            return Response(content=img_bytes, media_type="image/png")
        raise HTTPException(status_code=500, detail="Page rendering failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= ADD WATERMARK =================
@router.post("/add-watermark")
def add_watermark_api(
    file: UploadFile = File(...),
    watermark_text: str = Form("CONFIDENTIAL")
):
    """Add watermark to PDF"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_watermarked.pdf"

    try:
        success = add_watermark(file_path, output_path, watermark_text)

        if success:
            return return_pdf_file(output_path, "watermarked.pdf")
        else:
            raise HTTPException(status_code=500, detail="Watermark addition failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= ADD HEADER FOOTER =================
@router.post("/add-header-footer")
async def add_header_footer_api(
    file: UploadFile = File(...),
    header_text: str = Form(...),
    footer_text: str = Form(...)
):
    """Add header and footer to PDF"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_with_header_footer.pdf"
    
    try:
        success = add_header_footer(file_path, output_path, header_text, footer_text)
        
        if success:
            return return_pdf_file(output_path, "with_header_footer.pdf")
        else:
            raise HTTPException(status_code=500, detail="Header/footer addition failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


def normalize_improvement_level(level: str) -> str:
    """Map frontend improvement level to backend improvement type."""
    mapping = {
        "basic": "general",
        "intermediate": "clarity",
        "advanced": "engagement",
        "clarity": "clarity",
        "conciseness": "conciseness",
        "engagement": "engagement",
        "general": "general",
        "standard": "general"
    }
    return mapping.get(level.strip().lower(), "general")


# ================= IMPROVE WRITING =================
@router.post("/improve-writing")
async def improve_writing_api(file: UploadFile = File(...), level: str = Form("standard")):
    """Improve writing quality in PDF"""
    file_path = save_file(file, ".pdf")
    output_path = None

    try:
        text = extract_text_or_ocr(file_path)
        improvement_type = normalize_improvement_level(level)
        improved = improve_text_logic(text, improvement_type)

        output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_improved.pdf"
        pdf_file = generate_corrected_pdf(improved, output_path)
        
        response_data = {
            "status": "success",
            "improved_text": improved,
            "original_text_length": len(text)
        }
        
        if pdf_file and os.path.exists(pdf_file):
            with open(pdf_file, "rb") as f:
                pdf_bytes = f.read()
            response_data["pdf_base64"] = base64.b64encode(pdf_bytes).decode("utf-8")
            response_data["pdf_filename"] = "improved.pdf"
        else:
            response_data["note"] = "PDF generation not available for this content."
        
        return response_data

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)
        if output_path:
            cleanup_file(output_path)


# ================= FIX FORMATTING =================
@router.post("/fix-formatting")
async def fix_formatting_api(file: UploadFile = File(...)):
    """Fix formatting of PDF — preserves exact text positions, font sizes, and colours."""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_formatted.pdf"

    try:
        # ── Layout-preserving path: keeps original positions/sizes/fonts ──
        result_path = fix_formatting_pdf_layout(file_path, output_path)

        # Also extract text for the formatted_text field (used by frontend)
        try:
            formatted_text = extract_text_or_ocr(file_path)
        except Exception:
            formatted_text = ""

        response_data: dict = {
            "status": "success",
            "formatted_text": formatted_text,
            "original_text_length": len(formatted_text),
        }

        if result_path and os.path.exists(result_path):
            with open(result_path, "rb") as f:
                pdf_bytes = f.read()
            response_data["pdf_base64"] = base64.b64encode(pdf_bytes).decode("utf-8")
            response_data["pdf_filename"] = "formatted.pdf"
        else:
            response_data["note"] = "Layout-preserving PDF generation failed; try download as text."

        return response_data

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)
        if output_path:
            cleanup_file(output_path)

# ================= DETECT FORM FIELDS =================
@router.post("/detect-form-fields")
async def detect_form_fields(file: UploadFile = File(...)):
    """Detect ___ blank lines in a PDF and return them for filling."""
    file_path = save_file(file, ".pdf")
    try:
        from modules.blank_detector import find_blanks
        blanks = find_blanks(file_path)
        return {
            "status":  "success",
            "blanks":  blanks,
            "count":   len(blanks),
            "summary": f"Found {len(blanks)} blank field(s)." if blanks else "No blank fields detected.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= SMART FORM FILLING =================
@router.post("/fill-form")
async def fill_form(
    file: UploadFile = File(...),
    fills: str = Form(default="[]"),
    sig_meta: str = Form(default="{}"),
    sig_files: List[UploadFile] = File(default=[]),
):
    """
    Fill ___ blanks in a PDF.

    fills    : JSON list of {"full_line","blank","value","page","rect"}
    sig_meta : JSON dict  {"sig_0":{"full_line","rect","page"}, ...}
    sig_files: actual signature image files (sent as multipart file uploads)
    """
    file_path   = save_file(file, ".pdf")
    sig_paths   = []
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_filled.pdf"
    try:
        fill_list = json.loads(fills)
        meta_dict = json.loads(sig_meta)

        shutil.copy(file_path, output_path)

        # ── 1. Text replacements ──────────────────────────────────────────
        replace_map = {}
        for item in fill_list:
            full_line = item.get("full_line", "")
            blank_tok = item.get("blank", "")
            value     = item.get("value", "").strip()
            if not full_line or not value:
                continue
            if blank_tok and blank_tok in full_line:
                replace_map[full_line] = full_line.replace(blank_tok, value, 1)
            else:
                replace_map[full_line] = value

        if replace_map:
            add_text_replacement(output_path, output_path, replace_map)

        # ── 2. Signature placements ───────────────────────────────────────
        if sig_files and meta_dict:
            doc = fitz.open(output_path)

            for i, sig_upload in enumerate(sig_files):
                key  = f"sig_{i}"
                info = meta_dict.get(key)
                if not info:
                    continue

                rect_raw = info.get("rect")    # [x0, y0, x1, y1] of the blank line
                page_num = info.get("page", 0)

                # Read signature bytes
                sp = save_file(sig_upload, ".png")
                sig_paths.append(sp)
                with open(sp, "rb") as sf:
                    sig_bytes = sf.read()

                # ── Remove white/light background ─────────────────────────
                try:
                    from PIL import Image as _PIL
                    import io as _io
                    img = _PIL.open(_io.BytesIO(sig_bytes)).convert("RGBA")
                    data = img.getdata()
                    new_data = []
                    for r, g, b, a in data:
                        # Pixels brighter than threshold → transparent
                        if r > 210 and g > 210 and b > 210:
                            new_data.append((255, 255, 255, 0))
                        else:
                            new_data.append((r, g, b, a))
                    img.putdata(new_data)
                    buf = _io.BytesIO()
                    img.save(buf, format="PNG")
                    sig_bytes = buf.getvalue()
                    logging.info(f"BG removed for sig_{i}")
                except Exception as _e:
                    logging.warning(f"BG removal failed for sig_{i}: {_e}")

                # ── Place signature ON the blank line ─────────────────────
                page = doc[page_num]

                if rect_raw and len(rect_raw) == 4:
                    x0, y0, x1, y1 = rect_raw
                    blank_w = x1 - x0          # width of the blank line
                    blank_h = max(y1 - y0, 2)  # height of the drawn line (very thin)

                    # Signature height = 3× the blank width / aspect ratio
                    # Place it so its BOTTOM aligns with the blank line
                    sig_h = max(30, blank_w * 0.25)   # reasonable signature height
                    sig_rect = fitz.Rect(
                        x0,            # left edge of blank
                        y0 - sig_h,    # top = above the line
                        x1,            # right edge of blank
                        y1,            # bottom = exactly on the line
                    )
                else:
                    # Fallback: search for underscores on the page
                    full_line = info.get("full_line", "")
                    m    = re.search(r"_{4,}", full_line or "")
                    hits = page.search_for(m.group(0)) if m else []
                    if not hits and full_line:
                        hits = page.search_for(full_line)
                    if hits:
                        r = hits[0]
                        sig_rect = fitz.Rect(r.x0, r.y0 - 30, r.x1, r.y1)
                    else:
                        logging.warning(f"Could not locate blank for sig_{i}")
                        continue

                page.insert_image(sig_rect, stream=sig_bytes, keep_proportion=True)
                logging.info(f"Placed sig_{i} at {sig_rect} on page {page_num}")

            tmp = output_path + ".tmp"
            doc.save(tmp)
            doc.close()
            os.replace(tmp, output_path)

        return return_pdf_file(output_path, "filled_form.pdf")

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in fills")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)
        for sp in sig_paths:
            cleanup_file(sp)

# ================= CONVERT TO PDF =================
@router.post("/convert-to-pdf")
async def convert_to_pdf(file: UploadFile = File(...)):
    """Convert various file formats to PDF"""
    file_ext = os.path.splitext(file.filename)[1].lower()
    saved_path = save_file(file, file_ext)
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_converted.pdf"
    
    try:
        converter = FileConverter()
        input_format = file_ext.lstrip('.').lower()
        success = converter.convert_file(saved_path, output_path, input_format, 'pdf')
        
        if success:
            return return_pdf_file(output_path, "converted.pdf")
        else:
            raise HTTPException(status_code=500, detail=f"Conversion from {file_ext} failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(saved_path)


# ================= CONVERT FROM PDF =================
@router.post("/convert-from-pdf")
async def convert_from_pdf(
    file: UploadFile = File(...),
    output_format: str = Form(default="docx", alias="format")
):
    """Convert PDF to various formats"""
    file_path = save_file(file, ".pdf")
    
    try:
        converter = FileConverter()
        output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_converted.{output_format}"
        
        success = converter.convert_file(file_path, output_path, 'pdf', output_format)
        
        if success and os.path.exists(output_path):
            return FileResponse(output_path, media_type="application/octet-stream",
                              filename=f"converted.{output_format}",
                              background=BackgroundTask(cleanup_file, output_path))
        else:
            raise HTTPException(status_code=500, detail=f"Conversion to {output_format} failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= SUMMARIZE PDF =================
@router.post("/summarize-pdf")
async def summarize_pdf(file: UploadFile = File(...), summary_length: str = Form("medium")):
    """Summarize PDF content"""
    file_path = save_file(file, ".pdf")
    
    try:
        text = extract_text_or_ocr(file_path)
        summary = summarize_text(text, summary_length)
        key_points = extract_key_points(text)

        return {
            "status": "success",
            "summary": summary,
            "key_points": key_points,
            "original_length": len(text),
            "summary_length": len(summary)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= DETECT LANGUAGE =================
@router.post("/detect-language")
async def detect_language_api(file: UploadFile = File(...)):
    """
    Auto-detect the primary language of a PDF.
    Reads the first ~1500 chars of text and asks Groq to identify the language.
    Returns: {language_name, language_code, confidence}
    """
    file_path = save_file(file, ".pdf")
    try:
        text = extract_text_or_ocr(file_path)
        sample = text[:1500].strip() if text else ""

        if not sample:
            return {"language_name": "Unknown", "language_code": "auto", "confidence": "low", "sample": ""}

        from modules.translate import _groq_client, MODEL_PRIMARY, MODEL_FALLBACK, _GROQ_TIMEOUT
        if _groq_client is None:
            return {"language_name": "Unknown", "language_code": "auto", "confidence": "low", "sample": sample[:200]}

        prompt = (
            "Identify the primary language of this text. "
            "Respond ONLY with a JSON object in this exact format, no markdown:\n"
            '{"language_name": "English", "language_code": "en", "confidence": "high"}\n\n'
            f"Text sample:\n{sample[:800]}"
        )

        detected = {"language_name": "Unknown", "language_code": "auto", "confidence": "low"}
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
                raw_clean = re.sub(r"```[^\n]*\n?", "", raw).replace("```", "").strip()
                parsed = json.loads(raw_clean)
                detected = {
                    "language_name": parsed.get("language_name", "Unknown"),
                    "language_code": parsed.get("language_code", "auto"),
                    "confidence":    parsed.get("confidence", "medium"),
                    "sample":        sample[:200],
                }
                break
            except Exception as ex:
                logging.warning(f"Language detection ({model}): {ex}")

        return detected

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= TRANSLATE PDF (text only) =================
@router.post("/translate-pdf")
async def translate_pdf(
    file: UploadFile = File(...),
    source_language: str = Form("Auto Detect"),
    target_language: str = Form("Hindi"),
    text_only: str = Form("false"),
):
    """Translate PDF content — text extraction + translation."""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_translated.pdf"

    try:
        if text_only.lower() == "true":
            with open(file_path, "rb") as f:
                raw = f.read()
            try:
                text = raw.decode("utf-8")
            except Exception:
                text = raw.decode("latin-1", errors="replace")
        else:
            text = extract_text_or_ocr(file_path)

        if not text.strip():
            return {
                "status": "success",
                "translated_text": "[Empty page — no text to translate]",
                "source_language": source_language,
                "target_language": target_language,
            }

        src = None if source_language.lower() in {"auto detect", "auto", ""} else source_language
        translated = await translate_text(text, target_language, src)

        pdf_base64 = None
        if text_only.lower() != "true":
            try:
                pdf_file = generate_corrected_pdf(translated, output_path)
                if pdf_file and os.path.exists(pdf_file):
                    with open(pdf_file, "rb") as f:
                        pdf_base64 = base64.b64encode(f.read()).decode("utf-8")
            except Exception as pdf_err:
                logging.warning(f"Backend PDF generation failed: {pdf_err}")

        return {
            "status": "success",
            "translated_text": translated,
            "source_language": source_language,
            "target_language": target_language,
            "original_text_length": len(text),
            "pdf_base64": pdf_base64,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)
        if os.path.exists(output_path):
            cleanup_file(output_path)


# ================= TRANSLATE PDF OVERLAY (same layout, one page) =================

# Unicode font for Indic/multilingual scripts
_UNICODE_FONT_FILE = None
for _fp in [
    r"C:\Windows\Fonts\Nirmala.ttf",
    r"C:\Windows\Fonts\NirmalaB.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
]:
    if os.path.exists(_fp):
        _UNICODE_FONT_FILE = _fp
        break


def _extract_page_blocks(page) -> list:
    """
    Extract text BLOCKS from a PDF page.
    Each block = one logical paragraph/heading with its full bbox, font size, color.
    Returns list of dicts: {text, bbox, size, color, align}
    """
    blocks_out = []
    page_w = page.rect.width

    for blk in page.get_text("dict")["blocks"]:
        if blk.get("type") != 0:
            continue

        block_lines = []
        blk_x0 = blk["bbox"][0]
        blk_y0 = blk["bbox"][1]
        blk_x1 = blk["bbox"][2]
        blk_y1 = blk["bbox"][3]
        size = 11.0
        color_int = 0

        for line in blk.get("lines", []):
            line_text = ""
            for span in line.get("spans", []):
                t = span.get("text", "")
                if t:
                    line_text += t
                    size = span.get("size", size)
                    color_int = span.get("color", color_int)
            if line_text.strip():
                block_lines.append(line_text.strip())

        full_text = "\n".join(block_lines).strip()
        if not full_text:
            continue

        c = color_int
        color = (
            ((c >> 16) & 0xFF) / 255.0,
            ((c >>  8) & 0xFF) / 255.0,
            ( c        & 0xFF) / 255.0,
        )

        blk_center = (blk_x0 + blk_x1) / 2
        if abs(blk_center - page_w / 2) < page_w * 0.15:
            align = 1  # center
        elif blk_x0 > page_w * 0.55:
            align = 2  # right
        else:
            align = 0  # left

        blocks_out.append({
            "text":   full_text,
            "bbox":   (blk_x0, blk_y0, blk_x1, blk_y1),
            "size":   size,
            "color":  color,
            "align":  align,
        })

    return blocks_out


def _build_translated_page(src_doc, page_num: int, translated_blocks: list, font_file: str) -> fitz.Document:
    """
    Build a one-page PDF by copying the original page, then replacing only
    the detected text block areas with translated text.
    Layout, font size, color and alignment are preserved.
    Translated text that is longer than the original bbox gets extra height.
    """
    src_page = src_doc[page_num]
    pw = src_page.rect.width
    ph = src_page.rect.height
    page_margin = 28  # min distance from page edges

    out_doc = fitz.open()
    out_doc.insert_pdf(src_doc, from_page=page_num, to_page=page_num)
    out_page = out_doc[0]

    # Prefer a Unicode font (Nirmala, Arial) for Indic + multilingual scripts
    fk = ({"fontname": "nirmala", "fontfile": font_file}
          if font_file else {"fontname": "helv"})

    # ── 1. Redact all original text blocks first ─────────────────────────────
    for blk in translated_blocks:
        x0, y0, x1, y1 = blk["bbox"]
        out_page.add_redact_annot(
            fitz.Rect(x0 - 2, y0 - 2, x1 + 2, y1 + 2),
            fill=(1, 1, 1),
        )
    out_page.apply_redactions()

    # ── 2. Font size shrink steps (gentler: 5% per step instead of 12%) ──────
    def _font_steps(size: float) -> list:
        steps = []
        cur = float(size or 11)
        while cur >= 5.5:
            steps.append(round(cur, 2))
            cur *= 0.93   # 7% reduction each step — gentler than before
        steps.append(5.5)
        return steps

    # ── 3. Estimate how many lines text needs at a given font size ───────────
    def _estimate_lines(text: str, box_width: float, font_size: float) -> int:
        chars_per_line = max(1, box_width / (font_size * 0.55))
        words = text.split()
        lines = 1
        cur_len = 0
        for w in words:
            wl = len(w) + 1
            if cur_len + wl > chars_per_line:
                lines += 1
                cur_len = wl
            else:
                cur_len += wl
        return lines

    # ── 4. Insert each translated block ─────────────────────────────────────
    for blk in translated_blocks:
        x0, y0, x1, y1 = blk["bbox"]
        text  = blk["translated"]
        fs    = blk["size"]
        color = blk["color"]
        align = blk["align"]

        # Horizontal rect — center-aligned blocks get full width
        if align == 1:  # center
            rx0 = page_margin
            rx1 = pw - page_margin
        else:
            rx0 = max(page_margin, x0)
            rx1 = min(pw - page_margin, max(x1, x0 + 80))

        box_w = max(rx1 - rx0, 60)

        inserted = False
        for try_fs in _font_steps(fs):
            # Compute dynamic height — give enough room for translated text
            n_lines  = _estimate_lines(text, box_w, try_fs)
            line_h   = try_fs * 1.45          # generous line height
            need_h   = n_lines * line_h + 4
            orig_h   = max(y1 - y0, try_fs * 1.3)
            box_h    = max(orig_h, need_h)

            ry1 = min(ph - page_margin, y0 + box_h)
            rect = fitz.Rect(rx0, y0, rx1, ry1)

            ov = out_page.insert_textbox(
                rect, text,
                fontsize=try_fs,
                color=color,
                align=align,
                **fk,
            )
            if ov >= 0:
                inserted = True
                break

        # Last-resort fallback: truncate to first sentence/phrase
        if not inserted:
            # Try the full text at min size with max available height
            rect_full = fitz.Rect(rx0, y0, rx1, ph - page_margin)
            ov2 = out_page.insert_textbox(
                rect_full, text,
                fontsize=5.5,
                color=color,
                align=align,
                **fk,
            )
            if ov2 < 0:
                # Absolute last resort — truncate
                short = text[:120].rsplit(" ", 1)[0] + "…"
                out_page.insert_textbox(
                    rect_full, short,
                    fontsize=5.5,
                    color=color,
                    align=align,
                    **fk,
                )

    return out_doc


@router.post("/translate-pdf-overlay")
async def translate_pdf_overlay(
    file: UploadFile = File(...),
    source_language: str = Form("Auto Detect"),
    target_language: str = Form("Hindi"),
    page_num: int = Form(0),
    translation_mode: str = Form("Fast"),
):
    """Translate one PDF page preserving layout."""
    file_path   = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_overlay.pdf"

    try:
        with fitz.open(file_path) as src_doc:
            if page_num >= len(src_doc):
                raise HTTPException(status_code=400, detail="Page out of range")

            page = src_doc[page_num]
            blocks = _extract_page_blocks(page)

            src = None if source_language.lower() in {"auto detect", "auto", ""} else source_language

            if not blocks:
                page_doc = fitz.open()
                page_doc.insert_pdf(src_doc, from_page=page_num, to_page=page_num)
                page_doc.save(output_path)
                page_doc.close()
                return FileResponse(output_path, media_type="application/pdf",
                                    filename=f"translated_page_{page_num+1}.pdf",
                                    background=BackgroundTask(cleanup_file, output_path))

            raw_texts = [b["text"] for b in blocks]
            translated = translate_blocks_contextual(
                raw_texts,
                target_language,
                src,
                prefer_fast=translation_mode.strip().lower() == "fast",
            )
            for blk, tr in zip(blocks, translated):
                blk["translated"] = tr.strip() if tr.strip() else blk["text"]

            page_doc = _build_translated_page(src_doc, page_num, blocks, _UNICODE_FONT_FILE)
            page_doc.save(output_path)
            page_doc.close()

        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename=f"translated_page_{page_num + 1}.pdf",
            background=BackgroundTask(cleanup_file, output_path)
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"translate_pdf_overlay error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


@router.post("/translate-pdf-full")
async def translate_pdf_full(
    file: UploadFile = File(...),
    source_language: str = Form("Auto Detect"),
    target_language: str = Form("Hindi"),
    translation_mode: str = Form("Fast"),
):
    """
    Translate entire PDF preserving layout — same format, size, position.
    Steps:
      1. Extract all text blocks from every page (preserving bbox, font-size, color, alignment)
      2. Translate blocks in parallel with page-level context (meaning-based, not word-for-word)
      3. Redact original text areas and reinsert translated text at exact same positions
      4. Auto shrink font gently if translated text is longer than available space
    """
    file_path   = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_translated_full.pdf"

    src = None if source_language.lower() in {"auto detect", "auto", ""} else source_language
    prefer_fast = translation_mode.strip().lower() == "fast"

    try:
        # Open source doc — kept open until we finish building the output
        src_doc     = fitz.open(file_path)
        total_pages = len(src_doc)

        # ── Step 1: Extract all blocks from all pages ────────────────────────
        pages_blocks = [_extract_page_blocks(src_doc[pg]) for pg in range(total_pages)]

        # ── Step 2: Translate pages in parallel (page-level context) ─────────
        has_text = any(pages_blocks)
        if not has_text:
            # No extractable text blocks (scanned PDF) — fallback to OCR + text translation
            src_doc.close()
            logging.warning("No text blocks found (likely scanned PDF) - falling back to OCR translation.")
            
            try:
                # 1. Extract text via OCR
                ocr_text = extract_text_or_ocr(file_path)
                if not ocr_text.strip():
                    raise ValueError("No text could be extracted via OCR.")
                
                # 2. Translate full text
                # run_in_executor since translate_text is async, or we can just call it synchronously 
                # but translate_text is async, so we need asyncio here if we aren't already awaited. 
                # Since translate_pdf_full is async, we can await it!
                translated_ocr = await translate_text(ocr_text, target_language, src)
                
                # 3. Generate text-only PDF
                generated_pdf_path = generate_corrected_pdf(translated_ocr, output_path)
                if generated_pdf_path and os.path.exists(generated_pdf_path):
                    return FileResponse(
                        generated_pdf_path,
                        media_type="application/pdf",
                        filename="translated_scanned.pdf",
                        background=BackgroundTask(cleanup_file, generated_pdf_path),
                    )
            except Exception as e:
                logging.error(f"Fallback OCR translation failed: {e}")
            
            # If fallback fails, return original PDF
            import shutil as _sh
            _sh.copy(file_path, output_path)
            return FileResponse(
                output_path,
                media_type="application/pdf",
                filename="translated.pdf",
                background=BackgroundTask(cleanup_file, output_path),
            )

        def _translate_page_job(pg_num: int, blocks: list):
            raw_texts  = [blk["text"] for blk in blocks]
            translated = translate_blocks_contextual(
                raw_texts, target_language, src, prefer_fast=prefer_fast
            )
            return pg_num, translated

        page_jobs    = [(pn, blks) for pn, blks in enumerate(pages_blocks) if blks]
        worker_count = min(max(1, int(os.getenv("TRANSLATE_PAGE_WORKERS", "4"))), len(page_jobs))

        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = [
                pool.submit(_translate_page_job, pn, blks)
                for pn, blks in page_jobs
            ]
            for fut in as_completed(futures):
                pn, translated = fut.result()
                for blk, tr in zip(pages_blocks[pn], translated):
                    blk["translated"] = tr.strip() if tr.strip() else blk["text"]

        # ── Step 3: Build output PDF page by page ────────────────────────────
        final_doc = fitz.open()
        for pg_num in range(total_pages):
            blocks = pages_blocks[pg_num]
            if not blocks:
                # Image-only or blank page — copy verbatim
                final_doc.insert_pdf(src_doc, from_page=pg_num, to_page=pg_num)
            else:
                page_doc = _build_translated_page(src_doc, pg_num, blocks, _UNICODE_FONT_FILE)
                final_doc.insert_pdf(page_doc)
                page_doc.close()

        final_doc.save(output_path)
        final_doc.close()
        src_doc.close()

        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename="translated.pdf",
            background=BackgroundTask(cleanup_file, output_path),
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"translate_pdf_full error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= MERGE PDFS =================
@router.post("/merge-pdfs")
def merge_pdfs_api(
    files: List[UploadFile] = File(...),
    insert_after: int = Form(-1)
):
    """
    Merge multiple PDFs.
    insert_after: page number (1-based) after which to insert the extra PDFs.
                  -1 or 0 = append at end (default).
    """
    file_paths = []
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_merged.pdf"

    try:
        for file in files:
            file_paths.append(save_file(file, ".pdf"))

        if len(file_paths) < 2:
            raise HTTPException(status_code=400, detail="At least 2 PDFs required to merge")

        # If insert_after is specified and > 0, reorder: base[:insert_after] + extras + base[insert_after:]
        if insert_after > 0:
            base_path   = file_paths[0]
            extra_paths = file_paths[1:]

            base_doc  = fitz.open(base_path)
            total_pages = len(base_doc)
            insert_idx  = min(insert_after, total_pages)  # clamp

            # Build merged doc: base pages 0..insert_idx-1, then extras, then base insert_idx..end
            out_doc = fitz.open()
            out_doc.insert_pdf(base_doc, from_page=0, to_page=insert_idx - 1)

            for ep in extra_paths:
                extra_doc = fitz.open(ep)
                out_doc.insert_pdf(extra_doc)
                extra_doc.close()

            if insert_idx < total_pages:
                out_doc.insert_pdf(base_doc, from_page=insert_idx, to_page=total_pages - 1)

            base_doc.close()
            out_doc.save(output_path)
            out_doc.close()
            success = True
        else:
            # Default: append all in order
            success = merge_pdfs(file_paths, output_path)

        if success:
            return return_pdf_file(output_path, "merged.pdf")
        else:
            raise HTTPException(status_code=500, detail="PDF merge failed")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for fp in file_paths:
            cleanup_file(fp)


# ================= SPLIT PDF =================
@router.post("/split-pdf")
def split_pdf_api(file: UploadFile = File(...), start_page: int = Form(1), end_page: int = Form(None)):
    """Split PDF or extract specific pages"""
    file_path = save_file(file, ".pdf")
    output_dir = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_split"
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # If end_page is 0, make it None to go to the end
        if end_page is not None and end_page <= 0:
            end_page = None
            
        success = split_pdf(file_path, output_dir, start_page - 1, end_page)
        
        if success:
            zip_filename = f"{output_dir}.zip"
            shutil.make_archive(output_dir, 'zip', output_dir)
            return FileResponse(zip_filename, media_type="application/zip", filename="split_pdfs.zip", background=BackgroundTask(cleanup_file, zip_filename))
        else:
            raise HTTPException(status_code=500, detail="PDF split failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir, ignore_errors=True)


# ================= ADD IMAGE =================
@router.post("/add-image")
def add_image_api(
    file: UploadFile = File(...),
    image: UploadFile = File(...),
    page_num: int = Form(1),
    x: float = Form(0),
    y: float = Form(0),
    width: float = Form(100),
    height: float = Form(100)
):
    """Add image to PDF"""
    file_path = save_file(file, ".pdf")
    image_ext = os.path.splitext(image.filename)[1].lower()
    image_path = save_file(image, image_ext)
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_with_image.pdf"
    
    try:
        image_edits = [{
            "page": page_num - 1,
            "image_path": image_path,
            "x": x,
            "y": y,
            "width": width,
            "height": height
        }]
        success = add_image_to_pdf(file_path, output_path, image_edits)
        
        if success:
            return return_pdf_file(output_path, "with_image.pdf")
        else:
            raise HTTPException(status_code=500, detail="Image addition failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)
        cleanup_file(image_path)



# ================= COMPRESS PDF =================
@router.post("/compress-pdf")
def compress_pdf_api(file: UploadFile = File(...)):
    """Compress PDF to reduce file size"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_compressed.pdf"
    
    try:
        success = compress_pdf(file_path, output_path)
        
        if success:
            original_size = os.path.getsize(file_path)
            compressed_size = os.path.getsize(output_path)
            compression_ratio = ((original_size - compressed_size) / original_size) * 100

            return return_pdf_file(output_path, "compressed.pdf")
        else:
            raise HTTPException(status_code=500, detail="PDF compression failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= EXTRACT PAGES =================
@router.post("/extract-pages")
def extract_pages_api(file: UploadFile = File(...), pages: str = Form(...)):
    """Extract specific pages from PDF"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_extracted.pdf"
    
    try:
        # Parse page numbers (e.g., "1,3,5" or "1-5")
        page_list = []
        for part in pages.split(","):
            if "-" in part:
                start, end = map(int, part.split("-"))
                page_list.extend(range(start - 1, end))
            else:
                page_list.append(int(part) - 1)

        success = extract_pages(file_path, output_path, page_list)
        
        if success:
            return return_pdf_file(output_path, "extracted.pdf")
        else:
            raise HTTPException(status_code=500, detail="Page extraction failed")

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid page format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= ROTATE PAGES =================
@router.post("/rotate-pages")
def rotate_pages_api(file: UploadFile = File(...), angle: int = Form(90)):
    """Rotate PDF pages"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_rotated.pdf"
    
    try:
        success = rotate_pages(file_path, output_path, angle)
        
        if success:
            return return_pdf_file(output_path, "rotated.pdf")
        else:
            raise HTTPException(status_code=500, detail="Page rotation failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= DELETE PAGES =================
@router.post("/delete-pages")
def delete_pages_api(file: UploadFile = File(...), pages: str = Form(...)):
    """Delete specific pages from PDF"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_trimmed.pdf"
    
    try:
        # Parse page numbers
        page_list = []
        for part in pages.split(","):
            if "-" in part:
                start, end = map(int, part.split("-"))
                page_list.extend(range(start - 1, end))
            else:
                page_list.append(int(part) - 1)

        success = delete_pages(file_path, output_path, page_list)
        
        if success:
            return return_pdf_file(output_path, "trimmed.pdf")
        else:
            raise HTTPException(status_code=500, detail="Page deletion failed")

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid page format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= REORDER PAGES =================
@router.post("/reorder-pages")
def reorder_pages_api(file: UploadFile = File(...), order: str = Form(...)):
    """Reorder PDF pages"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_reordered.pdf"
    
    try:
        # Parse page order (e.g., "3,1,2")
        page_order = [int(p) - 1 for p in order.split(",")]
        
        success = reorder_pages(file_path, output_path, page_order)
        
        if success:
            return return_pdf_file(output_path, "reordered.pdf")
        else:
            raise HTTPException(status_code=500, detail="Page reordering failed")

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid page order format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= PDF INFO =================
@router.post("/pdf-info")
def get_pdf_info_api(file: UploadFile = File(...)):
    """Get detailed PDF information"""
    file_path = save_file(file, ".pdf")
    
    try:
        info = get_pdf_info(file_path)
        metadata = get_pdf_metadata(file_path)
        
        return {
            "status": "success",
            "info": info,
            "metadata": metadata,
            "file_size": os.path.getsize(file_path)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= HIGHLIGHT TEXT =================
@router.post("/highlight-text")
def highlight_text_api(
    file: UploadFile = File(...),
    text_to_highlight: str = Form(...),
    color: str = Form("yellow")
):
    """Highlight specific text in PDF"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_highlighted.pdf"
    
    try:
        color_map = {
            "yellow": (1, 1, 0),
            "green": (0.6, 1, 0.6),
            "blue": (0.6, 0.8, 1),
            "pink": (1, 0.75, 0.85),
        }
        success = highlight_text(
            file_path,
            output_path,
            [{"page": -1, "text": text_to_highlight, "color": color_map.get(color.lower(), (1, 1, 0))}],
        )
        
        if success:
            return return_pdf_file(output_path, "highlighted.pdf")
        else:
            raise HTTPException(status_code=500, detail="Text highlighting failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= ADD ANNOTATION =================
@router.post("/add-annotation")
def add_annotation_api(
    file: UploadFile = File(...),
    page_num: int = Form(1),
    comment: str = Form(...),
    annotation_type: str = Form("text")
):
    """Add annotation/comment to PDF"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_annotated.pdf"
    
    try:
        success = add_annotation(
            file_path,
            output_path,
            [{
                "page": page_num - 1,
                "type": "comment" if annotation_type == "text" else annotation_type,
                "text": comment,
                "x": 100,
                "y": 100,
            }],
        )
        
        if success:
            return return_pdf_file(output_path, "annotated.pdf")
        else:
            raise HTTPException(status_code=500, detail="Annotation addition failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= ADD BOOKMARK =================
@router.post("/add-bookmark")
def add_bookmark_api(file: UploadFile = File(...), bookmarks: str = Form(...)):
    """Add bookmarks/outline to PDF"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_bookmarked.pdf"
    
    try:
        # Parse bookmarks (e.g., "Chapter 1:1,Chapter 2:5")
        bookmark_dict = {}
        try:
            for item in bookmarks.split(","):
                title, page = item.split(":")
                bookmark_dict[title.strip()] = int(page) - 1
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid bookmark format")

        success = add_bookmark(file_path, output_path, bookmark_dict)
        
        if success:
            return return_pdf_file(output_path, "bookmarked.pdf")
        else:
            raise HTTPException(status_code=500, detail="Bookmark addition failed")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= DETECT BLANK PAGES =================
@router.post("/detect-blank-pages")
def detect_blank_pages(file: UploadFile = File(...)):
    """Detect blank pages in PDF"""
    file_path = save_file(file, ".pdf")

    try:
        blank_pages = []
        with fitz.open(file_path) as doc:
            for i, page in enumerate(doc):
                text = page.get_text().strip()
                images = page.get_images()
                drawings = page.get_drawings()
                if not text and not images and not drawings:
                    blank_pages.append(i + 1)  # 1-based page number

        return {
            "status": "success",
            "blank_pages": blank_pages,
            "blank_page_count": len(blank_pages)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= BATCH OPERATIONS =================
@router.post("/batch-process")
def batch_process(
    file: UploadFile = File(...),
    operations: str = Form(...)
):
    """Execute multiple operations in sequence"""
    file_path = save_file(file, ".pdf")
    current_path = file_path
    
    try:
        # Parse operations (e.g., "correct_text|improve_writing|add_watermark:DRAFT")
        ops = operations.split("|")
        results = []

        for op in ops:
            if ":" in op:
                op_name, op_param = op.split(":", 1)
            else:
                op_name = op
                op_param = None

            output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_{op_name}.pdf"

            try:
                if op_name == "correct_text":
                    text = extract_text_or_ocr(current_path)
                    corrected = correct_text(text)
                    result_path = generate_corrected_pdf(corrected, output_path)
                    
                elif op_name == "improve_writing":
                    text = extract_text_or_ocr(current_path)
                    improved = improve_text_logic(text, normalize_improvement_level(op_param or "standard"))
                    result_path = generate_corrected_pdf(improved, output_path)
                    
                elif op_name == "add_watermark":
                    result_path_success = add_watermark(current_path, output_path, op_param or "DRAFT")
                    result_path = output_path if result_path_success else None
                    
                else:
                    result_path = None

                if result_path and os.path.exists(result_path):
                    results.append({"operation": op_name, "status": "success"})
                    current_path = result_path
                else:
                    results.append({"operation": op_name, "status": "failed"})

            except Exception as e:
                results.append({"operation": op_name, "status": "error", "error": str(e)})

        return {
            "status": "success",
            "operations": results,
            "output_file": current_path
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= SET SECURITY =================
@router.post("/set-security")
def set_security_api(
    file: UploadFile = File(...),
    user_pw: str = Form(""),
    owner_pw: str = Form(""),
    allow_printing: bool = Form(True),
    allow_editing: bool = Form(True)
):
    """Set PDF password and permissions"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_secured.pdf"
    
    try:
        # Permissions bitmask (very simplified)
        permissions = -1 # All allowed
        if not allow_printing:
            permissions &= ~fitz.PDF_PERM_PRINT
        if not allow_editing:
            permissions &= ~fitz.PDF_PERM_MODIFY
            
        success = set_pdf_security(file_path, output_path, user_pw, owner_pw, permissions)
        if success:
            return return_pdf_file(output_path, "secured.pdf")
        else:
            raise HTTPException(status_code=500, detail="Security setting failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= PAGE NUMBERS =================
@router.post("/add-page-numbers")
def add_page_numbers_api(file: UploadFile = File(...), position: str = Form("bottom_right")):
    """Add page numbers to PDF"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_numbered.pdf"
    
    try:
        success = add_page_numbers(file_path, output_path, position)
        if success:
            return return_pdf_file(output_path, "with_page_numbers.pdf")
        else:
            raise HTTPException(status_code=500, detail="Page numbering failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= BACKGROUND COLOR =================
@router.post("/set-background")
def set_background_api(
    file: UploadFile = File(...),
    r: float = Form(1.0),
    g: float = Form(1.0),
    b: float = Form(1.0)
):
    """Set PDF background color"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_bg_colored.pdf"
    
    try:
        success = set_background_color(file_path, output_path, (r, g, b))
        if success:
            return return_pdf_file(output_path, "background_colored.pdf")
        else:
            raise HTTPException(status_code=500, detail="Background setting failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= CREATE FORM =================
@router.post("/create-form")
def create_form_api(file: UploadFile = File(...), fields_json: str = Form(...)):
    """Create new form fields in PDF"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_with_form.pdf"
    
    try:
        fields = json.loads(fields_json)
        success = create_form_fields(file_path, output_path, fields)
        if success:
            return return_pdf_file(output_path, "formatted_form.pdf")
        else:
            raise HTTPException(status_code=500, detail="Form creation failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= ADD BLANK PAGE =================
@router.post("/add-blank-page")
def add_blank_page_api(file: UploadFile = File(...), after_page: int = Form(-1)):
    """Add a blank page to PDF"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_page_added.pdf"
    
    try:
        success = add_blank_page(file_path, output_path, after_page)
        if success:
            return return_pdf_file(output_path, "added_page.pdf")
        else:
            raise HTTPException(status_code=500, detail="Page addition failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= CLEAN SIGNATURE + EXTRACT TEXT (combined) =================
@router.post("/clean-and-extract-signature")
async def clean_and_extract_signature(image: UploadFile = File(...)):
    """
    One-shot endpoint:
      1. Remove white/paper background → transparent PNG (ink only)
      2. Extract the handwritten name/text via Groq vision → Tesseract fallback
    Returns JSON: { clean_image_b64, extracted_text, status }
    """
    ext = os.path.splitext(image.filename or "sig.png")[1].lower() or ".png"
    image_path = save_file(image, ext)

    try:
        from PIL import Image as PILImage
        import cv2
        import numpy as np
        import base64 as _b64

        # ── Step 1: Remove white background ──────────────────────────────
        img_pil = PILImage.open(image_path).convert("RGBA")
        img_np  = np.array(img_pil)
        rgb     = img_np[:, :, :3]
        gray    = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

        # Upscale 2x for better edge detection
        scale    = 2
        gray_up  = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        rgb_up   = cv2.resize(rgb,  None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        _, mask = cv2.threshold(gray_up, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        kernel  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        mask    = cv2.dilate(mask, kernel, iterations=1)

        rgba_up = cv2.cvtColor(rgb_up, cv2.COLOR_RGB2RGBA)
        rgba_up[:, :, 3] = mask

        h, w = img_np.shape[:2]
        result = cv2.resize(rgba_up, (w, h), interpolation=cv2.INTER_AREA)

        # Tight crop around ink
        alpha  = result[:, :, 3]
        coords = cv2.findNonZero(alpha)
        if coords is not None:
            x, y, bw, bh = cv2.boundingRect(coords)
            pad = 8
            result = result[
                max(0, y - pad): min(h, y + bh + pad),
                max(0, x - pad): min(w, x + bw + pad)
            ]

        import io as _io
        clean_buf = _io.BytesIO()
        PILImage.fromarray(result, "RGBA").save(clean_buf, format="PNG")
        clean_bytes  = clean_buf.getvalue()
        clean_b64    = _b64.b64encode(clean_bytes).decode("utf-8")

        # ── Step 2: Extract text ──────────────────────────────────────────
        extracted = ""

        # Strategy 1: Groq vision on the ORIGINAL image (better for handwriting)
        try:
            from groq import Groq as _Groq
            _api_key = os.getenv("GROQ_API_KEY", "").strip()
            if _api_key and _api_key != "your_groq_api_key_here":
                _client = _Groq(api_key=_api_key)
                with open(image_path, "rb") as _f:
                    _img_b64 = _b64.b64encode(_f.read()).decode("utf-8")
                _mime = "image/png" if ext == ".png" else "image/jpeg"
                _resp = _client.chat.completions.create(
                    model="meta-llama/llama-4-scout-17b-16e-instruct",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image_url",
                             "image_url": {"url": f"data:{_mime};base64,{_img_b64}"}},
                            {"type": "text",
                             "text": (
                                 "This is a handwritten signature image. "
                                 "Read and extract the person's name written in this signature. "
                                 "Return ONLY the name, nothing else. "
                                 "If you cannot read it clearly, return your best guess."
                             )}
                        ]
                    }],
                    max_tokens=50,
                    temperature=0,
                )
                extracted = (_resp.choices[0].message.content or "").strip().strip('"\'')
        except Exception as _ve:
            logging.warning(f"Groq vision failed: {_ve}")

        # Strategy 2: Tesseract on the cleaned (ink-only) image
        if not extracted:
            try:
                import pytesseract
                # Use the clean ink image for OCR — no background noise
                clean_pil = PILImage.open(_io.BytesIO(clean_bytes)).convert("L")
                # Invert: Tesseract expects dark text on white
                clean_inv = PILImage.fromarray(255 - np.array(clean_pil))
                best = ""
                for psm in [7, 8, 6, 13]:
                    r = pytesseract.image_to_string(clean_inv, config=f"--oem 3 --psm {psm}").strip()
                    r = " ".join(r.split())
                    if len(r) > len(best) and len(r) < 80:
                        best = r
                extracted = best
            except Exception as _te:
                logging.warning(f"Tesseract fallback failed: {_te}")

        extracted = " ".join(extracted.split())

        return {
            "status": "success",
            "clean_image_b64": clean_b64,
            "extracted_text": extracted,
        }

    except Exception as e:
        logging.error(f"clean-and-extract-signature error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(image_path)


# ================= EXTRACT TEXT FROM IMAGE (General OCR) =================
@router.post("/extract-text-from-image")
async def extract_text_from_image(image: UploadFile = File(...)):
    """
    General-purpose OCR: extract any printed or handwritten text from an image.
    Strategy:
      1. Groq vision — best for both printed and handwritten content
      2. Fallback: Tesseract with print-optimised config
    """
    ext = os.path.splitext(image.filename or "img.png")[1].lower() or ".png"
    image_path = save_file(image, ext)

    try:
        from PIL import Image as PILImage
        import cv2
        import numpy as np

        # ── Preprocess ────────────────────────────────────────────
        img_pil = PILImage.open(image_path).convert("RGB")
        img_np  = np.array(img_pil)
        gray    = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

        # Upscale small images for better OCR accuracy
        h, w = gray.shape
        if w < 600:
            scale = 600 / w
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        # Light denoise then threshold
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        extracted = ""

        # ── Strategy 1: Groq vision ───────────────────────────────
        try:
            from groq import Groq as _Groq
            import base64 as _b64
            _api_key = os.getenv("GROQ_API_KEY", "").strip()
            if _api_key and _api_key != "your_groq_api_key_here":
                _client = _Groq(api_key=_api_key)
                with open(image_path, "rb") as _f:
                    _img_b64 = _b64.b64encode(_f.read()).decode("utf-8")
                _mime = "image/png" if ext == ".png" else "image/jpeg"
                _resp = _client.chat.completions.create(
                    model="meta-llama/llama-4-scout-17b-16e-instruct",
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{_mime};base64,{_img_b64}"}
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Extract ALL text visible in this image exactly as it appears. "
                                    "Include printed text, typed text, handwriting, numbers, dates — everything. "
                                    "Return ONLY the extracted text, nothing else. "
                                    "Preserve line breaks where they exist."
                                )
                            }
                        ]
                    }],
                    max_tokens=300,
                    temperature=0,
                )
                extracted = (_resp.choices[0].message.content or "").strip().strip('"\'')
        except Exception as _ve:
            logging.warning(f"Groq vision OCR failed: {_ve}")

        # ── Strategy 2: Tesseract (print-optimised) ───────────────
        if not extracted:
            try:
                import pytesseract
                pil_thresh = PILImage.fromarray(thresh)
                best = ""
                # PSM 6 = uniform block of text, PSM 3 = auto, PSM 4 = single column
                for psm in [6, 3, 4, 11]:
                    cfg = f"--oem 3 --psm {psm}"
                    result = pytesseract.image_to_string(pil_thresh, config=cfg).strip()
                    result = " ".join(result.split())
                    if len(result) > len(best):
                        best = result
                extracted = best
            except Exception as _te:
                logging.warning(f"Tesseract OCR failed: {_te}")

        extracted = " ".join(extracted.split())  # final whitespace cleanup

        return {
            "status": "success",
            "extracted_text": extracted,
            "confidence": "high" if extracted else "low"
        }

    except Exception as e:
        logging.error(f"Image text extraction error: {e}")
        return {"status": "error", "extracted_text": "", "error": str(e)}
    finally:
        cleanup_file(image_path)


# ================= EXTRACT SIGNATURE TEXT =================
@router.post("/extract-signature-text")
async def extract_signature_text(image: UploadFile = File(...)):
    """
    Extract handwritten name/text from a signature image.
    Strategy:
      1. Try Groq vision (llama-4-scout) — best for handwriting
      2. Fallback: multi-config Tesseract with heavy preprocessing
    """
    ext = os.path.splitext(image.filename)[1].lower() or ".png"
    image_path = save_file(image, ext)

    try:
        from PIL import Image as PILImage
        import cv2
        import numpy as np

        # ── Load & preprocess ──────────────────────────────────────
        img_pil = PILImage.open(image_path).convert("RGB")
        img_np  = np.array(img_pil)
        gray    = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

        # Upscale 4x for better detail
        gray = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)

        # Denoise
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        # OTSU threshold — better than adaptive for signatures
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # ── Strategy 1: Groq vision model ─────────────────────────
        extracted = ""
        try:
            from groq import Groq as _Groq
            import base64 as _b64
            _api_key = os.getenv("GROQ_API_KEY", "").strip()
            _client = None
            if _api_key and _api_key != "your_groq_api_key_here":
                try:
                    _client = _Groq(api_key=_api_key)
                    logging.info("✅ Groq vision client initialized")
                except Exception as _e:
                    logging.warning(f"Groq vision init failed: {_e}")
            if _client:
                # Encode original image as base64
                with open(image_path, "rb") as _f:
                    _img_b64 = _b64.b64encode(_f.read()).decode("utf-8")
                _mime = "image/png" if ext in [".png"] else "image/jpeg"
                _resp = _client.chat.completions.create(
                    model="meta-llama/llama-4-scout-17b-16e-instruct",
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{_mime};base64,{_img_b64}"}
                            },
                            {
                                "type": "text",
                                "text": (
                                    "This is a handwritten signature image. "
                                    "Read and extract the person's name written in this signature. "
                                    "Return ONLY the name, nothing else. "
                                    "If you cannot read it clearly, return your best guess."
                                )
                            }
                        ]
                    }],
                    max_tokens=50,
                    temperature=0,
                )
                extracted = (_resp.choices[0].message.content or "").strip()
                # Remove quotes if model wrapped the name
                extracted = extracted.strip('"\'')
        except Exception as _ve:
            logging.warning(f"Vision model failed: {_ve}")

        # ── Strategy 2: Tesseract multi-config fallback ────────────
        if not extracted:
            try:
                import pytesseract
                pil_thresh = PILImage.fromarray(thresh)
                best = ""
                for psm in [7, 8, 6, 13]:
                    cfg = f"--oem 3 --psm {psm}"
                    result = pytesseract.image_to_string(pil_thresh, config=cfg).strip()
                    result = " ".join(result.split())
                    # Pick the longest plausible result
                    if len(result) > len(best) and len(result) < 60:
                        best = result
                extracted = best
            except Exception as _te:
                logging.warning(f"Tesseract fallback failed: {_te}")

        extracted = " ".join(extracted.split())  # final cleanup

        return {
            "status": "success",
            "extracted_text": extracted,
            "confidence": "high" if extracted else "low"
        }

    except Exception as e:
        logging.error(f"Signature extraction error: {e}")
        return {"status": "error", "extracted_text": "", "error": str(e)}
    finally:
        cleanup_file(image_path)


# ================= REMOVE SIGNATURE BACKGROUND =================
@router.post("/remove-signature-bg")
async def remove_signature_bg(image: UploadFile = File(...)):
    """
    Remove white/paper background from a signature image.
    Returns a transparent PNG with only the ink strokes.
    """
    ext = os.path.splitext(image.filename)[1].lower() or ".png"
    image_path = save_file(image, ext)
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_sig_clean.png"

    try:
        from PIL import Image as PILImage
        import cv2
        import numpy as np

        img = PILImage.open(image_path).convert("RGBA")
        img_np = np.array(img)

        # Work on RGB channels
        rgb = img_np[:, :, :3]
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

        # Upscale for better edge detection
        scale = 2
        gray_up = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        rgb_up  = cv2.resize(rgb,  None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        # OTSU threshold — separates ink from paper
        _, mask = cv2.threshold(gray_up, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Slight dilation to keep thin strokes intact
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        mask = cv2.dilate(mask, kernel, iterations=1)

        # Build RGBA output: ink pixels keep original color, background → transparent
        rgba_up = cv2.cvtColor(rgb_up, cv2.COLOR_RGB2RGBA)
        rgba_up[:, :, 3] = mask  # alpha = ink mask

        # Downscale back to original size
        h, w = img_np.shape[:2]
        result = cv2.resize(rgba_up, (w, h), interpolation=cv2.INTER_AREA)

        # Crop to tight bounding box around the signature
        alpha = result[:, :, 3]
        coords = cv2.findNonZero(alpha)
        if coords is not None:
            x, y, bw, bh = cv2.boundingRect(coords)
            pad = 6
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(w, x + bw + pad)
            y2 = min(h, y + bh + pad)
            result = result[y1:y2, x1:x2]

        PILImage.fromarray(result, "RGBA").save(output_path, "PNG")

        return FileResponse(
            output_path,
            media_type="image/png",
            filename="signature_clean.png",
            background=BackgroundTask(cleanup_file, output_path)
        )

    except Exception as e:
        logging.error(f"Signature BG removal error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(image_path)
