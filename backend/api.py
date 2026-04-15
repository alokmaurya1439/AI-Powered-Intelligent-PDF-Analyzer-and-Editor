import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response, FileResponse
from starlette.background import BackgroundTask
import os
import shutil
import json
import logging
import base64
from typing import List
from dotenv import load_dotenv

# ========== Importing modules ==============
from modules.pdf_reader import extract_text_or_ocr, get_pdf_metadata
from modules.error_detector import detect_errors, detect_pdf_issues, check_text_quality
from modules.error_solver import correct_text, correct_pdf_layout_safe, generate_corrected_pdf
from modules.error_solver import improve_writing as improve_text_logic
from modules.error_solver import fix_formatting as fix_format_logic
from modules.summarizer import summarize_text, extract_key_points
from modules.translate import translate_text
from modules.blank_detector import find_blank_in_file
from modules.file_converter import FileConverter
from modules.pdf_editor import (
    add_text_replacement, add_image_to_pdf, merge_pdfs,
    split_pdf, add_watermark, add_header_footer,
    draw_shape, highlight_text, get_form_fields, fill_form_pdf,
    add_annotation, compress_pdf, add_bookmark,
    get_pdf_info, delete_pages, extract_pages,
    reorder_pages, rotate_pages
)

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
async def error_detector(file: UploadFile = File(...)):
    """Detect errors, issues, and quality in PDF"""
    file_path = save_file(file, ".pdf")
    
    try:
        # Extract text and metadata
        text = extract_text_or_ocr(file_path)
        metadata = get_pdf_metadata(file_path)
        
        # Detect errors and issues
        errors = detect_errors(text)
        issues = detect_pdf_issues(file_path)
        quality = check_text_quality(text)

        return {
            "status": "success",
            "text": text[:1000],  # First 1000 chars
            "metadata": metadata,
            "quality": quality,
            "issues": issues,
            "errors": errors,
            "text_length": len(text)
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
        # Extract and correct text
        text = extract_text_or_ocr(file_path)
        corrected = correct_text(text)

        # Try layout-safe correction
        try:
            result = correct_pdf_layout_safe(file_path, output_path, clean_output_path)
            pdf_file = result.get("layout_pdf") if isinstance(result, dict) else None
        except Exception as e:
            print(f"Layout correction failed: {e}")
            pdf_file = None

        # Fallback: regenerate PDF
        if not pdf_file or not os.path.exists(pdf_file):
            pdf_file = generate_corrected_pdf(corrected, output_path)

        # If PDF generation still failed, return the text instead
        if not pdf_file or not os.path.exists(pdf_file):
            return {
                "status": "success",
                "message": "PDF generation not available for this content. Text provided instead.",
                "corrected_text": corrected,
                "original_text_length": len(text),
                "corrected_text_length": len(corrected)
            }

        return return_pdf_file(pdf_file, "corrected.pdf")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)
        cleanup_file(clean_output_path)


# ================= REPLACE TEXT =================
@router.post("/replace-text")
async def replace_text(file: UploadFile = File(...), old_text: str = Form(...), new_text: str = Form(...)):
    """Replace specific text in PDF"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_replaced.pdf"
    
    try:
        success = add_text_replacement(file_path, output_path, {old_text: new_text})
        
        if success:
            return return_pdf_file(output_path, "replaced.pdf")
        else:
            raise HTTPException(status_code=500, detail="Text replacement failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


# ================= ADD WATERMARK =================
@router.post("/add-watermark")
async def add_watermark_api(file: UploadFile = File(...), watermark_text: str = Form(...)):
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
    """Fix formatting issues in PDF"""
    file_path = save_file(file, ".pdf")
    output_path = None

    try:
        text = extract_text_or_ocr(file_path)
        fixed = fix_format_logic(text)

        output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_formatted.pdf"
        pdf_file = generate_corrected_pdf(fixed, output_path)
        
        response_data = {
            "status": "success",
            "formatted_text": fixed,
            "original_text_length": len(text)
        }
        
        if pdf_file and os.path.exists(pdf_file):
            with open(pdf_file, "rb") as f:
                pdf_bytes = f.read()
            response_data["pdf_base64"] = base64.b64encode(pdf_bytes).decode("utf-8")
            response_data["pdf_filename"] = "formatted.pdf"
        else:
            response_data["note"] = "PDF generation not available for this content."
        
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
    """Detect blank spaces/form fields in PDF"""
    file_path = save_file(file, ".pdf")
    
    try:
        from modules.blank_detector import find_blank_in_file
        blanks = find_blank_in_file(file_path)
        fields = get_form_fields(file_path)
        
        placeholders = []
        if isinstance(blanks, dict):
            placeholders = blanks.get("text_placeholders", [])
            
        return {
            "status": "success",
            "fields": fields,
            "placeholders": placeholders
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)

# ================= SMART FORM FILLING =================
@router.post("/fill-form")
async def fill_form(
    file: UploadFile = File(...), 
    form_data: str = Form(default="{}"),
    text_replacements: str = Form(default="{}")
):
    """Fill PDF form with data and text replacements for blank placeholders"""
    file_path = save_file(file, ".pdf")
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_filled.pdf"
    
    try:
        data_dict = json.loads(form_data)
        replace_dict = json.loads(text_replacements)
        
        import shutil
        shutil.copy(file_path, output_path)
        
        if data_dict:
            fill_form_pdf(output_path, output_path, data_dict)
            
        if replace_dict:
            # We can use add_text_replacement to fill the visual blank placeholders
            from modules.pdf_editor import add_text_replacement
            add_text_replacement(output_path, output_path, replace_dict)
        
        return return_pdf_file(output_path, "filled_form.pdf")
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON data")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)


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


# ================= TRANSLATE PDF =================
@router.post("/translate-pdf")
async def translate_pdf(
    file: UploadFile = File(...),
    source_language: str = Form("en"),
    target_language: str = Form("es")
):
    """Translate PDF content and generate output PDF"""
    file_path = save_file(file, ".pdf")
    output_path = None

    try:
        text = extract_text_or_ocr(file_path)
        translated = await translate_text(text, target_language, source_language)

        output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_translated.pdf"
        
        # Try to generate PDF with translated text
        pdf_file = None
        pdf_base64 = None
        pdf_filename = f"translated_{target_language.lower()}.pdf"
        
        try:
            # Attempt PDF generation
            pdf_file = generate_corrected_pdf(translated, output_path)
            if pdf_file and os.path.exists(pdf_file):
                with open(pdf_file, "rb") as f:
                    pdf_bytes = f.read()
                pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
        except Exception as pdf_error:
            # Log but don't fail - continue with text-only response
            print(f"PDF generation warning: {pdf_error}")
            pdf_base64 = None

        response_data = {
            "status": "success",
            "translated_text": translated,
            "source_language": source_language,
            "target_language": target_language,
            "original_text_length": len(text)
        }
        
        if pdf_base64:
            response_data["pdf_base64"] = pdf_base64
            response_data["pdf_filename"] = pdf_filename
        else:
            response_data["note"] = "PDF generation unavailable for this language pair. Text download provided instead."
        
        return response_data

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cleanup_file(file_path)
        if output_path and os.path.exists(output_path):
            cleanup_file(output_path)


# ================= MERGE PDFS =================
@router.post("/merge-pdfs")
def merge_pdfs_api(files: List[UploadFile] = File(...)):
    """Merge multiple PDFs into one"""
    file_paths = []
    output_path = f"{OUTPUT_DIR}/{uuid.uuid4().hex}_merged.pdf"
    
    try:
        # Save all files
        for file in files:
            file_paths.append(save_file(file, ".pdf"))

        # Merge
        success = merge_pdfs(file_paths, output_path)
        
        if success:
            return return_pdf_file(output_path, "merged.pdf")
        else:
            raise HTTPException(status_code=500, detail="PDF merge failed")

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

        success = extract_pages(file_path, page_list, output_path)
        
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

        success = delete_pages(file_path, page_list, output_path)
        
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
        
        success = reorder_pages(file_path, page_order, output_path)
        
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
            [{"page": 0, "text": text_to_highlight, "color": color_map.get(color.lower(), (1, 1, 0))}],
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
        blank_pages = find_blank_in_file(file_path)
        
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
                    result_path_success = add_watermark(current_path, op_param or "DRAFT", output_path)
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
