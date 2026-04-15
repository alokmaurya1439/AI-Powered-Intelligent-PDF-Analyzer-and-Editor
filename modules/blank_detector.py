from pypdf import PdfReader
import logging
import re
from typing import Dict
from modules.pdf_reader import extract_text_or_ocr

logging.basicConfig(level=logging.INFO)

def find_blank_in_file(file_path: str) -> Dict:
    """
    Detect blank form fields and placeholder lines in a PDF.

    Args:
        file_path (str): Path to the PDF file

    Returns:
        dict: structured blank field information
    """

    result = {
        "form_fields": [],          # list of empty form field names
        "text_placeholders": []     # list of lines with blanks
    }

    # ================= FORM FIELD DETECTION =================
    try:
        reader = PdfReader(file_path)

        root = reader.trailer.get("/Root", {})
        if "/AcroForm" in root:
            form = root["/AcroForm"]
            fields = form.get("/Fields", [])

            for fld in fields:
                try:
                    field_obj = fld.get_object()

                    name = field_obj.get("/T", "<unnamed>")
                    value = field_obj.get("/V", "")

                    if not value or str(value).strip() == "":
                        result["form_fields"].append(name)

                except Exception as e:
                    logging.warning(f"Field parse error: {e}")

    except Exception as e:
        logging.warning(f"⚠ Form parsing failed: {e}")

    # ================= TEXT PLACEHOLDER DETECTION =================
    try:
        text = extract_text_or_ocr(file_path)

        for line in text.splitlines():
            clean_line = line.strip()

            if not clean_line:
                continue

            # 🔍 Detect placeholders
            if (
                re.search(r"_{4,}", clean_line) or        # _______
                re.search(r"\[\s{2,}\]", clean_line) or   # [    ]
                re.search(r"\(\s{2,}\)", clean_line) or   # (    )
                re.search(r":\s{3,}", clean_line)         # Name:     ___
            ):
                result["text_placeholders"].append(clean_line)

    except Exception as e:
        logging.warning(f"⚠ Text analysis failed: {e}")

    # ================= FINAL RESPONSE =================
    if not result["form_fields"] and not result["text_placeholders"]:
        return {"message": "No blank fields or placeholders detected"}

    return result