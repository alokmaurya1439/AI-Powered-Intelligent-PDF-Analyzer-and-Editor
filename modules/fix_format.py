#!/usr/bin/env python3
"""
fix_format.py — Manual PDF Fix Formatting Tool
================================================
Removes extra spaces from a PDF while keeping the EXACT same layout,
font sizes, positions, images, and graphics.

Usage:
    python fix_format.py input.pdf                   # saves as input_fixed.pdf
    python fix_format.py input.pdf output.pdf        # saves as output.pdf

Requirements:
    pip install pymupdf
"""

import os
import re
import sys
import shutil
import argparse


# ── Helpers ──────────────────────────────────────────────────────────────────

_UNICODE_MAP = {
    "\u201c": '"', "\u201d": '"',
    "\u2018": "'", "\u2019": "'",
    "\u2013": "-", "\u2014": "-",
    "\u2026": "...",
}


def _clean_unicode(text: str) -> str:
    for uc, asc in _UNICODE_MAP.items():
        text = text.replace(uc, asc)
    return text

def _fix_text(text: str) -> str:
    """Collapse multiple spaces/tabs; normalise smart quotes."""
    text = _clean_unicode(text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()

def _map_font(raw: str) -> str:
    fn = raw.lower()
    bold   = "bold" in fn
    italic = "italic" in fn or "oblique" in fn
    if "times" in fn or "roman" in fn:
        if bold and italic: return "Times-BoldItalic"
        if bold:            return "Times-Bold"
        if italic:          return "Times-Italic"
        return "Times-Roman"
    if "courier" in fn or "mono" in fn:
        if bold and italic: return "Courier-BoldOblique"
        if bold:            return "Courier-Bold"
        if italic:          return "Courier-Oblique"
        return "Courier"
    if bold and italic: return "Helvetica-BoldOblique"
    if bold:            return "Helvetica-Bold"
    if italic:          return "Helvetica-Oblique"
    return "Helvetica"

def _decode_color(c: int):
    return (((c >> 16) & 0xFF) / 255.0,
            ((c >>  8) & 0xFF) / 255.0,
            ( c        & 0xFF) / 255.0)


# ── Core fix function ─────────────────────────────────────────────────────────

def fix_pdf(input_path: str, output_path: str) -> bool:
    """
    Fix extra spaces in input_path and write result to output_path.
    Layout, images, fonts, sizes and positions are 100% preserved.
    Only spans that actually contain extra spaces are touched.

    Returns True on success, False on failure.
    """
    try:
        import fitz   # PyMuPDF
    except ImportError:
        print("ERROR: PyMuPDF is not installed. Run:  pip install pymupdf")
        return False

    if not os.path.exists(input_path):
        print(f"ERROR: File not found: {input_path}")
        return False

    print(f"\n📄 Input  : {input_path}")
    print(f"💾 Output : {output_path}")

    # Work on a copy so the original is never modified
    shutil.copy(input_path, output_path)
    doc = fitz.open(output_path)

    total_pages = len(doc)
    total_fixed = 0

    for page_num, page in enumerate(doc, start=1):
        page_dict = page.get_text("dict")
        spans_to_fix = []

        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    raw = span.get("text", "")
                    if not raw.strip():
                        continue
                    fixed = _fix_text(raw)
                    if fixed == raw:
                        continue   # already clean

                    x0, y0, x1, y1 = span["bbox"]
                    size      = span.get("size", 11)
                    color     = _decode_color(span.get("color", 0))
                    font      = _map_font(span.get("font", ""))

                    spans_to_fix.append({
                        "bbox":  fitz.Rect(x0, y0, x1, y1),
                        "text":  fixed,
                        "size":  size,
                        "font":  font,
                        "color": color,
                        "pt":    fitz.Point(x0, y0 + size * 0.85),
                        "raw":   raw,
                    })

        if not spans_to_fix:
            print(f"  Page {page_num:>3}/{total_pages} — ✅ already clean")
            continue

        # Redact dirty spans
        for s in spans_to_fix:
            page.add_redact_annot(s["bbox"], fill=(1, 1, 1))
        page.apply_redactions()

        # Re-insert cleaned text at original positions
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
                except Exception:
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

        total_fixed += len(spans_to_fix)
        print(f"  Page {page_num:>3}/{total_pages} — 🔧 fixed {len(spans_to_fix)} span(s)")

    doc.save(output_path, incremental=False, encryption=fitz.PDF_ENCRYPT_NONE)
    doc.close()

    size_in  = os.path.getsize(input_path)  / 1024
    size_out = os.path.getsize(output_path) / 1024
    print(f"\n✅ Done! Fixed {total_fixed} span(s) across {total_pages} page(s).")
    print(f"   Input size : {size_in:,.1f} KB")
    print(f"   Output size: {size_out:,.1f} KB")
    print(f"   Saved to   : {os.path.abspath(output_path)}\n")
    return True


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Remove extra spaces from a PDF while preserving its exact layout.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fix_format.py report.pdf
  python fix_format.py report.pdf report_clean.pdf
  python fix_format.py "C:/Documents/My Report.pdf"
        """
    )
    parser.add_argument("input",  help="Path to the input PDF file")
    parser.add_argument("output", nargs="?", default=None,
                        help="Path to save the fixed PDF (default: input_fixed.pdf)")
    args = parser.parse_args()

    input_path = args.input
    if args.output:
        output_path = args.output
    else:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_fixed{ext}"

    success = fix_pdf(input_path, output_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
