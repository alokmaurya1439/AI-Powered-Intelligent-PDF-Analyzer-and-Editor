import cv2
import io
import os
import fitz  # PyMuPDF
import numpy as np
import pytesseract
from PIL import Image
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict, List, Tuple

# ================ CONFIG ================
# Allow environment-configured tesseract path for portability
pytesseract.pytesseract.tesseract_cmd = os.getenv(
    'TESSERACT_CMD',
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)
CONF_THRESHOLD = 40  # reduced for better recall

# ================ IMAGE PREPROCESS ================

def preprocess_image(image: Image.Image):
    """Denoise and threshold the input image for OCR reliability."""
    img = np.array(image)

    if img.ndim == 2:
        gray = img
    else:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Replace extremely slow fastNlMeansDenoising with fast median filtering
    denoise = cv2.medianBlur(gray, 3)

    thresh = cv2.adaptiveThreshold(
        denoise,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11,
        2,
    )

    return Image.fromarray(thresh)

# ================= ROTATION FIX =================
def correct_rotation(image: Image.Image) -> Image.Image:
    try:
        osd = pytesseract.image_to_osd(image)
        angle = int([line for line in osd.split("\n") if "Rotate" in line][0].split(":")[1])
        if angle != 0:
            image = image.rotate(-angle, expand=True)
    except:
        pass
    return image


# ================ OCR SINGLE PAGE ================

def ocr_page(page_data: Tuple[int, bytes]) -> List[Dict[str, Any]]:
    """OCR a page (image bytes) and return recognized text blocks."""
    page_num, img_bytes = page_data
    blocks: List[Dict[str, Any]] = []
    try:
        image = Image.open(io.BytesIO(img_bytes))
        image = correct_rotation(image)
        image = preprocess_image(image)

        data = pytesseract.image_to_data(
            image,
            lang="eng+hin+guj",
            config="--oem 3 --psm 6",
            output_type=pytesseract.Output.DICT,
        )

        # -------- GROUP WORDS INTO LINES --------
        lines = {}

        for i, word in enumerate(data.get("text", [])):
            if not word or not word.strip():
                continue

            try:
                conf = float(data.get("conf", [])[i])
            except (ValueError, IndexError):
                conf = 0.0

           
            if conf < CONF_THRESHOLD:
                continue

            line_num = data["line_num"][i]

            x = int(data.get("left", [0])[i])
            y = int(data.get("top", [0])[i])
            w = int(data.get("width", [0])[i])
            h = int(data.get("height", [0])[i])
            
            if line_num not in lines:
                lines[line_num] = {
                    "words": [],
                    "bbox": [x, y, x + w, y + h]
                }
            lines[line_num]["words"].append(word)

            # Expand bbox
            lines[line_num]["bbox"][0] = min(lines[line_num]["bbox"][0], x)
            lines[line_num]["bbox"][1] = min(lines[line_num]["bbox"][1], y)
            lines[line_num]["bbox"][2] = max(lines[line_num]["bbox"][2], x + w)
            lines[line_num]["bbox"][3] = max(lines[line_num]["bbox"][3], y + h)
            
        # Convert lines → blocks
        for line in lines.values():
            blocks.append(
                {
                    "page": page_num,
                    "bbox": tuple(line["bbox"]),
                    "text": " ".join(line["words"]),
                    "size": line["bbox"][3] - line["bbox"][1],
                    "font": "ocr",
                    "conf": 100.0,
                }
            )

    except Exception as e:
        print(f"⚠ OCR error on page {page_num}: {e}")

    return blocks


# ================ PAGE TYPE HELPERS ================

def is_text_page(page: fitz.Page, min_text_len: int = 50) -> bool:
    """Decide if page has selectable text (non-scanned)."""
    text = page.get_text().strip() if page else ""
    return len(text) > min_text_len


def extract_text_blocks(page: fitz.Page, page_num: int) -> List[Dict[str, Any]]:
    """Extract text blocks from a searchable PDF page."""
    blocks: List[Dict[str, Any]] = []
    data = page.get_text("dict")

    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            line_text = []
            bbox = [9999, 9999, 0, 0]

            for span in line.get("spans", []):
                span_text = span.get("text", "").strip()
                if not span_text:
                    continue

                
                line_text.append(span_text)

                x0, y0, x1, y1 = span.get("bbox", (0, 0, 0, 0))
                bbox[0] = min(bbox[0], x0)
                bbox[1] = min(bbox[1], y0)
                bbox[2] = max(bbox[2], x1)
                bbox[3] = max(bbox[3], y1)

            if line_text:
                blocks.append({
                    "page": page_num,
                    "bbox": tuple(bbox),
                    "text": " ".join(line_text),
                    "size": 12,
                    "font": "text",
                    "conf": 100.0,
                })

    return blocks


# ================ MAIN OCR ENGINE ================

def ocr_pdf_blocks(file_path: str) -> List[Dict[str, Any]]:
    """Hybrid OCR engine. Returns page-by-page text blocks with layout info."""
    doc = fitz.open(file_path)
    all_blocks: List[Dict[str, Any]] = []
    ocr_tasks: List[Tuple[int, bytes]] = []

    try:
        for page_num, page in enumerate(doc):
            if is_text_page(page):
                all_blocks.extend(extract_text_blocks(page, page_num))
            else:
                # 1x scale reduces image resolution by 4x compared to 2x, speeding up Tesseract massively
                pix = page.get_pixmap(matrix=fitz.Matrix(1, 1))
                img_bytes = pix.tobytes("png")
                ocr_tasks.append((page_num, img_bytes))

        if ocr_tasks:
            with ProcessPoolExecutor() as executor:
                results = list(executor.map(ocr_page, ocr_tasks))
                for page_blocks in results:
                    all_blocks.extend(page_blocks)

    finally:
        doc.close()

    return all_blocks


def ocr_pdf_text(file_path: str) -> str:
    """Return full text from PDF, mixing extracted and OCRed content."""
    blocks = ocr_pdf_blocks(file_path)
    sorted_blocks = sorted(blocks, key=lambda b: (b["page"], b["bbox"][1], b["bbox"][0]))
    return "\n".join(block["text"] for block in sorted_blocks)  