"""
AI Smart PDF Editor - PDF Manual Editing Module
Comprehensive PDF editing capabilities using PyMuPDF (fitz)
"""

import fitz  # PyMuPDF
import os
import logging
from typing import List, Dict, Optional


# ================= CONFIG =================
logging.basicConfig(level=logging.INFO) 

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def _check_file(path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

# ================= TEXT EDITING =================
def edit_text(input_path: str, output_path: str, edits: List[Dict]) -> bool:
    """
    Edit text in PDF by replacing or redacting content.
    
    Args:
        input_path: Path to original PDF
        output_path: Path to save edited PDF
        edits: List of dicts with keys:
            - page (int): Page number
            - old_text (str): Text to find and replace
            - new_text (str): Replacement text
            - x (float): X coordinate for new text
            - y (float): Y coordinate for new text
            - font_size (int): Font size (default 12)
            - color (tuple): RGB color tuple (default black)
    
    Returns:
        bool: Success status
    """
    try:
        _check_file(input_path)
        doc = fitz.open(input_path)

        for edit in edits:
            page_num = edit.get("page", 0)
            if page_num >= len(doc):
                continue
                
            page = doc[page_num]

            # Remove old text by redaction
            if edit.get("old_text"):
                areas = page.search_for(edit["old_text"])
                for rect in areas:
                    page.add_redact_annot(rect)
                page.apply_redactions()

            # Add new text
            if edit.get("new_text"):
                page.insert_text(
                    (edit.get("x", 50), edit.get("y", 50)),
                    edit["new_text"],
                    fontsize=edit.get("font_size", 12),
                    color=edit.get("color", (0, 0, 0))
                )

        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error editing text: {e}")
        return False


# ================= IMAGE INSERTION =================
def add_image_to_pdf(input_path: str, output_path: str, image_edits: List[Dict]) -> bool:
    """
    Insert images into PDF pages.
    
    Args:
        input_path: Path to original PDF
        output_path: Path to save edited PDF
        image_edits: List of dicts with keys:
            - page (int): Page number
            - image_path (str): Path to image file
            - x (float): X coordinate
            - y (float): Y coordinate
            - width (float): Image width
            - height (float): Image height
    
    Returns:
        bool: Success status
    """
    try:
        doc = fitz.open(input_path)

        for edit in image_edits:
            page_num = edit.get("page", 0)
            if page_num >= len(doc):
                continue
                
            page = doc[page_num]
            rect = fitz.Rect(
                edit["x"],
                edit["y"],
                edit["x"] + edit["width"],
                edit["y"] + edit["height"]
            )
            page.insert_image(rect, filename=edit["image_path"])

        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error inserting image: {e}")
        return False


# ================= TEXT REPLACEMENT =================
def add_text_replacement(input_path: str, output_path: str, replacements: Dict[str, str]) -> bool:
    """
    Replace text throughout the PDF.
    
    Args:
        input_path: Path to original PDF
        output_path: Path to save edited PDF
        replacements: Dict mapping old_text -> new_text
    
    Returns:
        bool: Success status
    """
    try:
        doc = fitz.open(input_path)

        for page in doc:
            for old_text, new_text in replacements.items():
                areas = page.search_for(old_text)
                if not areas:
                    continue

                first_rect = areas[0]
                for rect in areas:
                    page.add_redact_annot(rect)
                page.apply_redactions()
                page.insert_text(first_rect.top_left, new_text)

        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error replacing text: {e}")
        return False


# ================= DELETE PAGES =================
def delete_pages(input_path: str, output_path: str, page_numbers: List[int]) -> bool:
    """
    Delete specific pages from PDF.
    
    Args:
        input_path: Path to original PDF
        output_path: Path to save edited PDF
        page_numbers: List of page indices to delete (0-based)
    
    Returns:
        bool: Success status
    """
    try:
        doc = fitz.open(input_path)
        
        # Sort in reverse to avoid index shifting
        for page_num in sorted(page_numbers, reverse=True):
            if 0 <= page_num < len(doc):
                doc.delete_page(page_num)

        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error deleting pages: {e}")
        return False


# ================= ROTATE PAGES =================
def rotate_pages(input_path: str, output_path: str, rotations) -> bool:
    """
    Rotate specific pages.
    
    Args:
        input_path: Path to original PDF
        output_path: Path to save edited PDF
        rotations: Dict mapping page_num -> rotation_angle (0, 90, 180, 270)
    
    Returns:
        bool: Success status
    """
    try:
        doc = fitz.open(input_path)

        if isinstance(rotations, int):
            rotations = {page_num: rotations for page_num in range(len(doc))}

        for page_num, angle in rotations.items():
            if 0 <= page_num < len(doc):
                doc[page_num].set_rotation(angle)

        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error rotating pages: {e}")
        return False


# ================= MERGE PDFs =================
def merge_pdfs(pdf_paths: List[str], output_path: str) -> bool:
    """
    Merge multiple PDFs into one.
    
    Args:
        pdf_paths: List of PDF file paths to merge
        output_path: Path to save merged PDF
    
    Returns:
        bool: Success status
    """
    try:
        merged_doc = fitz.open()

        for pdf_path in pdf_paths:
            doc = fitz.open(pdf_path)
            merged_doc.insert_pdf(doc)
            doc.close()

        merged_doc.save(output_path)
        merged_doc.close()
        return True
    except Exception as e:
        print(f"❌ Error merging PDFs: {e}")
        return False


# ================= SPLIT PDF =================
def split_pdf(input_path: str, output_dir: str, start_page: int = 0, end_page: Optional[int] = None) -> bool:
    """
    Split PDF into separate files or page ranges.
    
    Args:
        input_path: Path to original PDF
        output_dir: Directory to save split PDFs
        start_page: Starting page index (0-based)
        end_page: Ending page index (inclusive)
    
    Returns:
        bool: Success status
    """
    try:
        doc = fitz.open(input_path)
        os.makedirs(output_dir, exist_ok=True)

        if end_page is None:
            end_page = len(doc) - 1

        for i in range(start_page, min(end_page + 1, len(doc))):
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=i, to_page=i)
            
            output_path = os.path.join(output_dir, f"page_{i+1}.pdf")
            new_doc.save(output_path)
            new_doc.close()

        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error splitting PDF: {e}")
        return False


# ================= ADD WATERMARK =================
def add_watermark(input_path: str, output_path: str, text: str, opacity: float = 0.3) -> bool:
    """
    Add text watermark to all pages.
    
    Args:
        input_path: Path to original PDF
        output_path: Path to save watermarked PDF
        text: Watermark text
        opacity: Opacity level (0.0 to 1.0)
    
    Returns:
        bool: Success status
    """
    try:
        doc = fitz.open(input_path)

        for page in doc:
            # Add semi-transparent text watermark
            page.insert_text(
                (page.rect.width / 4, page.rect.height / 2),
                text,
                fontsize=60,
                color=(0.5, 0.5, 0.5),
                alpha=opacity,
                rotate=45
            )

        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error adding watermark: {e}")
        return False


# ================= ADD HEADER/FOOTER =================
def add_header_footer(input_path: str, output_path: str, header: str = "", footer: str = "") -> bool:
    """
    Add header and/or footer to all pages.
    
    Args:
        input_path: Path to original PDF
        output_path: Path to save edited PDF
        header: Header text
        footer: Footer text
    
    Returns:
        bool: Success status
    """
    try:
        doc = fitz.open(input_path)

        for page_num, page in enumerate(doc):
            if header:
                page.insert_text(
                    (50, 30),
                    header,
                    fontsize=10,
                    color=(0, 0, 0)
                )
            
            if footer:
                page.insert_text(
                    (50, page.rect.height - 30),
                    footer,
                    fontsize=10,
                    color=(0, 0, 0)
                )

        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error adding header/footer: {e}")
        return False


# ================= DRAW SHAPES =================
def draw_shape(input_path: str, output_path: str, shapes: List[Dict]) -> bool:
    """
    Draw rectangles, circles, lines on PDF.
    
    Args:
        input_path: Path to original PDF
        output_path: Path to save edited PDF
        shapes: List of dicts with keys:
            - type (str): 'rectangle', 'circle', 'line'
            - page (int): Page number
            - x1, y1, x2, y2 (float): Coordinates
            - color (tuple): RGB color
            - width (float): Line width
    
    Returns:
        bool: Success status
    """
    try:
        doc = fitz.open(input_path)

        for shape in shapes:
            page_num = shape.get("page", 0)
            if page_num >= len(doc):
                continue
                
            page = doc[page_num]
            shape_type = shape.get("type", "rectangle")
            color = shape.get("color", (0, 0, 0))
            width = shape.get("width", 1)

            if shape_type == "rectangle":
                rect = fitz.Rect(shape["x1"], shape["y1"], shape["x2"], shape["y2"])
                page.draw_rect(rect, color=color, width=width)

            elif shape_type == "circle":
                center = fitz.Point(shape["x1"], shape["y1"])
                radius = shape.get("radius", 10)
                page.draw_circle(center, radius, color=color, width=width)

            elif shape_type == "line":
                p1 = fitz.Point(shape["x1"], shape["y1"])
                p2 = fitz.Point(shape["x2"], shape["y2"])
                page.draw_line(p1, p2, color=color, width=width)

        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error drawing shapes: {e}")
        return False


# ================= REORDER PAGES =================
def reorder_pages(input_path: str, output_path: str, page_order: List[int]) -> bool:
    """
    Reorder pages in PDF.
    
    Args:
        input_path: Path to original PDF
        output_path: Path to save edited PDF
        page_order: List of page indices in desired order (0-based)
    
    Returns:
        bool: Success status
    """
    try:
        original_doc = fitz.open(input_path)
        new_doc = fitz.open()

        for page_num in page_order:
            if 0 <= page_num < len(original_doc):
                new_doc.insert_pdf(original_doc, from_page=page_num, to_page=page_num)

        new_doc.save(output_path)
        new_doc.close()
        original_doc.close()
        return True
    except Exception as e:
        print(f"❌ Error reordering pages: {e}")
        return False


# ================= HIGHLIGHT TEXT =================
def highlight_text(input_path: str, output_path: str, highlights: List[Dict]) -> bool:
    """
    Highlight text passages in PDF.
    
    Args:
        input_path: Path to original PDF
        output_path: Path to save edited PDF
        highlights: List of dicts with keys:
            - page (int): Page number
            - text (str): Text to highlight
            - color (tuple): RGB color (default yellow)
    
    Returns:
        bool: Success status
    """
    try:
        doc = fitz.open(input_path)

        for highlight in highlights:
            page_num = highlight.get("page", 0)
            if page_num >= len(doc):
                continue
                
            page = doc[page_num]
            text = highlight.get("text", "")
            color = highlight.get("color", (1, 1, 0))  # Yellow default

            areas = page.search_for(text)
            for rect in areas:
                page.draw_rect(rect, color=color, fill=color, width=0)

        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error highlighting text: {e}")
        return False


# ================= FILL FORM FIELDS =================
def get_form_fields(input_path: str) -> List[Dict]:
    """
    Extract all form fields / blank spaces from a PDF.
    
    Args:
        input_path: Path to PDF
    
    Returns:
        List of dictionaries with field information
    """
    try:
        doc = fitz.open(input_path)
        fields = []
        
        for page in doc:
            for widget in page.widgets():
                fields.append({
                    "name": widget.field_name,
                    "type": widget.field_type_string,
                    "value": widget.field_value
                })
                
        doc.close()
        # Return unique fields
        unique_fields = {f["name"]: f for f in fields if f["name"]}.values()
        return list(unique_fields)
    except Exception as e:
        print(f"❌ Error extracting form fields: {e}")
        return []

def fill_form_pdf(input_path: str, output_path: str, field_values: Dict[str, str]) -> bool:
    """
    Fill form fields in PDF.
    
    Args:
        input_path: Path to PDF form
        output_path: Path to save filled PDF
        field_values: Dict mapping field_name -> value
    
    Returns:
        bool: Success status
    """
    try:
        doc = fitz.open(input_path)

        for page in doc:
            widgets = page.widgets() or []
            for widget in widgets:
                if widget.field_name in field_values:
                    widget.field_value = field_values[widget.field_name]
                    widget.update()

        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error filling form fields: {e}")
        return False


# ================= ADD ANNOTATIONS =================
def add_annotation(input_path: str, output_path: str, annotations) -> bool:
    """
    Add annotations (comments, notes) to PDF.
    
    Args:
        input_path: Path to original PDF
        output_path: Path to save annotated PDF
        annotations: List of dicts with keys:
            - page (int): Page number
            - type (str): 'comment', 'highlight', 'underline', 'strikeout'
            - text (str): Annotation text
            - x1, y1, x2, y2 (float): Coordinates for highlight
    
    Returns:
        bool: Success status
    """
    try:
        doc = fitz.open(input_path)

        if isinstance(annotations, dict):
            annotations = [annotations]

        for annot in annotations:
            page_num = annot.get("page", 0)
            if page_num >= len(doc):
                continue
                
            page = doc[page_num]
            annot_type = annot.get("type", "comment")
            
            if annot_type == "comment":
                point = fitz.Point(annot.get("x", 100), annot.get("y", 100))
                page.add_text_annot(point, annot.get("text", ""))
            
            elif annot_type in ["highlight", "underline", "strikeout"]:
                rect = fitz.Rect(annot["x1"], annot["y1"], annot["x2"], annot["y2"])
                
                if annot_type == "highlight":
                    page.add_highlight_annot(rect)
                elif annot_type == "underline":
                    page.add_underline_annot(rect)
                elif annot_type == "strikeout":
                    page.add_strikeout_annot(rect)

        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error adding annotations: {e}")
        return False


# ================= COMPRESS PDF =================
def compress_pdf(input_path: str, output_path: str) -> bool:
    """
    Compress PDF to reduce file size.
    
    Args:
        input_path: Path to original PDF
        output_path: Path to save compressed PDF
    
    Returns:
        bool: Success status
    """
    try:
        doc = fitz.open(input_path)
        doc.save(output_path, deflate=True)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error compressing PDF: {e}")
        return False


# ================= EXTRACT PAGES =================
def extract_pages(input_path: str, output_path: str, page_numbers: List[int]) -> bool:
    """
    Extract specific pages into new PDF.
    
    Args:
        input_path: Path to original PDF
        output_path: Path to save extracted PDF
        page_numbers: List of page indices to extract (0-based)
    
    Returns:
        bool: Success status
    """
    try:
        original_doc = fitz.open(input_path)
        new_doc = fitz.open()

        for page_num in sorted(page_numbers):
            if 0 <= page_num < len(original_doc):
                new_doc.insert_pdf(original_doc, from_page=page_num, to_page=page_num)

        new_doc.save(output_path)
        new_doc.close()
        original_doc.close()
        return True
    except Exception as e:
        print(f"❌ Error extracting pages: {e}")
        return False


# ================= ADD BOOKMARK =================
def add_bookmark(input_path: str, output_path: str, bookmarks) -> bool:
    """
    Add bookmarks/outline to PDF.
    
    Args:
        input_path: Path to original PDF
        output_path: Path to save PDF with bookmarks
        bookmarks: List of dicts with keys:
            - title (str): Bookmark title
            - page (int): Page number
            - level (int): Nesting level
    
    Returns:
        bool: Success status
    """
    try:
        doc = fitz.open(input_path)

        if isinstance(bookmarks, dict):
            bookmarks = [
                {"title": title, "page": page, "level": 1}
                for title, page in bookmarks.items()
            ]

        toc = []
        for bookmark in bookmarks:
            title = bookmark.get("title", "")
            page = bookmark.get("page", 0)
            level = max(1, int(bookmark.get("level", 1)))
            
            if title and 0 <= page < len(doc):
                toc.append([level, title, page + 1])

        if toc:
            doc.set_toc(toc)

        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error adding bookmarks: {e}")
        return False


# ================= UTILITY: GET PDF INFO =================
def get_pdf_info(file_path: str) -> Dict:
    """
    Get information about a PDF file.
    
    Args:
        file_path: Path to PDF file
    
    Returns:
        Dict with PDF metadata and page count
    """
    try:
        doc = fitz.open(file_path)
        info = {
            "page_count": len(doc),
            "metadata": doc.metadata,
            "file_size": os.path.getsize(file_path),
            "encrypted": doc.is_encrypted
        }
        doc.close()
        return info
    except Exception as e:
        print(f"❌ Error getting PDF info: {e}")
        return {}
