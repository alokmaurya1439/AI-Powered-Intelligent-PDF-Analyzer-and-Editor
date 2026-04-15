import os
import fitz  # PyMuPDF
import logging
from typing import Dict
from modules.ocr_engine import ocr_pdf_blocks

# ================= CONFIG =================
logging.basicConfig(level=logging.INFO)

OCR_THRESHOLD = 100  # minimum characters before triggering OCR


# ========== TEXT EXTRACTION ============
def extract_text_or_ocr(file_path: str, ocr_threshold: int = OCR_THRESHOLD) -> str:
    """
    Extract text from PDF. If text extraction yields nothing or below threshold, uses OCR fallback.
    Args:
        file_path (str): Path to the PDF file
        ocr_threshold (int): Minimum character count to skip OCR

    Returns:
        str: Extracted text
    """
    if not os.path.isfile(file_path):
        logging.error(f"File not found: {file_path}")
        return ""

    text_parts = []

    try:
        with fitz.open(file_path) as pdf:
            for page in pdf:
                page_text = page.get_text("text")
                # ✅ Fix: avoid empty spaces
                if page_text and page_text.strip():
                    text_parts.append(page_text.strip())
        text = "\n".join(text_parts)
        
        # 🔥 If text is empty or below threshold → OCR
        if not text_parts or sum(len(part) for part in text_parts) < ocr_threshold:
            logging.warning("⚠ Using OCR...")
            try:
                blocks = ocr_pdf_blocks(file_path)
                # ✅ Sort blocks (page → top → left)
                blocks_sorted = sorted(
                    blocks,
                    key=lambda b: (b["page"], b["bbox"][1], b["bbox"][0])
                )

                text = "\n".join(
                    block.get("text", "").strip()
                    for block in blocks_sorted
                    if block.get("text")
                )

            except Exception as ocr_error:
                logging.error(f"❌ OCR failed: {ocr_error}")
                return ""

        return text

    except Exception as e:
        logging.error(f"❌ Error extracting text: {e}")
        return ""


# ================= METADATA =================
def get_pdf_metadata(file_path: str) -> Dict:
    """
    Extract metadata from PDF.

    Returns:
        dict
    """

    if not os.path.isfile(file_path):
        return {"error": f"File not found: {file_path}"}

    try:
        with fitz.open(file_path) as pdf:
            metadata = pdf.metadata or {}

            # ✅ Remove empty values
            clean_metadata = {
                key: value for key, value in metadata.items()
                if value not in [None, "", " "]
            }

            if not clean_metadata:
                return {"message": "No metadata found"}

            return clean_metadata

    except Exception as e:
        return {"error": str(e)}


# ================= SIMPLE EXTRACTION =================
def extract_text_from_pdf(file_path: str) -> str:
    """
    Simple text extraction (no OCR fallback)

    Args:
        file_path (str): Path to PDF

    Returns:
        str: Extracted text
    """

    if not os.path.isfile(file_path):
        logging.error(f"❌ File not found: {file_path}")
        return ""

    try:
        text_parts = []

        with fitz.open(file_path) as pdf:
            for page in pdf:
                page_text = page.get_text("text")

                if page_text and page_text.strip():
                    text_parts.append(page_text.strip())

        return "\n".join(text_parts)

    except Exception as e:
        logging.error(f"❌ Error extracting text: {e}")
        return ""