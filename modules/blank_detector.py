"""
Blank Detector — detects ___ (underscore) blank lines in PDFs.
Each blank is tagged is_signature=True if its label contains signature keywords.
Also returns the exact bounding rect of the ___ token on the page.
"""
import re
import logging
from typing import Dict, List, Optional

import fitz

logging.basicConfig(level=logging.INFO)

_SIG_KEYWORDS = [
    "signature", "sign", "signed", "autograph",
    "hastakshar", "हस्ताक्षर", "सही", "સહી",
]


def _is_signature_label(label: str) -> bool:
    low = label.lower()
    return any(kw in low for kw in _SIG_KEYWORDS)


def _find_blank_rect(page: fitz.Page, blank_tok: str) -> Optional[List[float]]:
    """
    Find the exact bounding rect of the underscore token on the page.
    Returns [x0, y0, x1, y1] or None.
    """
    hits = page.search_for(blank_tok)
    if hits:
        r = hits[0]
        return [r.x0, r.y0, r.x1, r.y1]
    return None


def find_blanks(file_path: str) -> List[Dict]:
    """
    Scan every page of the PDF for lines containing 4+ underscores (____).

    Returns a list of dicts:
        {
            "index":        int,
            "label":        str,   # text before the blank
            "blank":        str,   # the raw underscore token
            "full_line":    str,   # complete line text
            "page":         int,   # 0-based page number
            "rect":         list,  # [x0, y0, x1, y1] of the ___ on the page (or None)
            "is_signature": bool,
        }
    """
    results = []
    try:
        with fitz.open(file_path) as doc:
            idx = 0
            for page_num, page in enumerate(doc):
                text = page.get_text("text") or ""
                for raw_line in text.splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    m = re.search(r"_{4,}", line)
                    if not m:
                        continue
                    blank_tok = m.group(0)
                    pos       = m.start()
                    label     = line[:pos].strip().rstrip(":").strip()
                    blank_rect = _find_blank_rect(page, blank_tok)
                    results.append({
                        "index":        idx,
                        "label":        label or f"Blank {idx + 1}",
                        "blank":        blank_tok,
                        "full_line":    line,
                        "page":         page_num,
                        "rect":         blank_rect,   # exact position of ___
                        "is_signature": _is_signature_label(label),
                    })
                    idx += 1
    except Exception as e:
        logging.error(f"Blank detection failed: {e}")

    return results
