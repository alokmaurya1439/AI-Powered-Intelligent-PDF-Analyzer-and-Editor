"""
PDF Reader Module — fast hybrid text extraction for small, medium, and large PDFs.
- Selectable-text pages : direct PyMuPDF extraction (instant)
- Scanned/image pages   : Tesseract OCR in memory-bounded batches
"""
import os
import fitz
import logging
from typing import Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO)

_OCR_BATCH = 8          # pages per OCR batch (caps RAM)
_OCR_WORKERS = 4        # parallel Tesseract processes per batch
_TEXT_THRESHOLD = 50    # min chars to consider a page "has text"


# ─────────────────────────────────────────────
def extract_text_or_ocr(file_path: str, max_pages: int = None) -> str:
    """
    Extract text from any PDF efficiently.
    max_pages: if set, only process the first N pages (useful for large PDFs).
    Works for small (1-10p), medium (10-100p), and large (100p+) PDFs.
    """
    if not os.path.isfile(file_path):
        logging.error(f"File not found: {file_path}")
        return ""

    text_parts: List[Tuple[int, str]] = []

    try:
        from modules.ocr_engine import ocr_page
        from concurrent.futures import ProcessPoolExecutor

        with fitz.open(file_path) as pdf:
            total = len(pdf)
            page_limit = min(total, max_pages) if max_pages else total
            ocr_batch: List[Tuple[int, bytes]] = []

            def _flush(batch: List[Tuple[int, bytes]]) -> None:
                if not batch:
                    return
                try:
                    workers = min(_OCR_WORKERS, len(batch))
                    with ProcessPoolExecutor(max_workers=workers) as ex:
                        results = list(ex.map(ocr_page, batch))
                    for (pg, _), blocks in zip(batch, results):
                        sorted_b = sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))
                        pg_text = "\n".join(b["text"].strip() for b in sorted_b if b.get("text"))
                        if pg_text.strip():
                            text_parts.append((pg, pg_text.strip()))
                except Exception as e:
                    logging.error(f"OCR batch error: {e}")

            for page_num, page in enumerate(pdf):
                if page_num >= page_limit:
                    break
                raw = page.get_text("text")
                if raw and len(raw.strip()) > _TEXT_THRESHOLD:
                    text_parts.append((page_num, raw.strip()))
                else:
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img_bytes = pix.tobytes("png")
                    pix = None
                    ocr_batch.append((page_num, img_bytes))
                    if len(ocr_batch) >= _OCR_BATCH:
                        logging.info(f"OCR flush at page {page_num + 1}/{page_limit}")
                        _flush(ocr_batch)
                        ocr_batch = []

            _flush(ocr_batch)

        text_parts.sort(key=lambda x: x[0])
        result = "\n\n".join(p[1] for p in text_parts)
        return result if result.strip() else extract_text_from_pdf(file_path)

    except Exception as e:
        logging.error(f"extract_text_or_ocr failed: {e}")
        return extract_text_from_pdf(file_path)


# ─────────────────────────────────────────────
def get_pdf_metadata(file_path: str) -> Dict:
    if not os.path.isfile(file_path):
        return {"error": f"File not found: {file_path}"}
    try:
        with fitz.open(file_path) as pdf:
            meta = {k: v for k, v in (pdf.metadata or {}).items()
                    if v not in [None, "", " "]}
            return meta if meta else {"message": "No metadata found"}
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────
def extract_text_from_pdf(file_path: str) -> str:
    """Simple direct extraction — no OCR fallback."""
    if not os.path.isfile(file_path):
        return ""
    try:
        with fitz.open(file_path) as pdf:
            parts = [page.get_text("text").strip() for page in pdf]
            return "\n".join(p for p in parts if p)
    except Exception as e:
        logging.error(f"extract_text_from_pdf failed: {e}")
        return ""
