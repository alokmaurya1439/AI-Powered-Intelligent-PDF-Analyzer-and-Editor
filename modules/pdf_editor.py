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

# ================= VISUAL DATA EXTRACTION =================
def get_page_text_blocks(file_path: str, page_num: int) -> List[Dict]:
    """Extract all text blocks from a page for direct 'Word-like' editing."""
    blocks_out = []
    try:
        _check_file(file_path)
        doc = fitz.open(file_path)
        if page_num < 0 or page_num >= len(doc): return []
        page = doc[page_num]
        p_dict = page.get_text("dict")
        for block in p_dict.get("blocks", []):
            if block.get("type") != 0: continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span["text"].strip()
                    if not text: continue
                    c = span["color"]
                    color = (((c >> 16) & 0xFF) / 255.0, ((c >> 8) & 0xFF) / 255.0, (c & 0xFF) / 255.0)
                    blocks_out.append({"text": text, "bbox": span["bbox"], "font": span["font"], "size": span["size"], "color": color})
        doc.close()
    except Exception as e:
        logging.error(f"Error extracting blocks: {e}")
    return blocks_out

def get_page_image(file_path: str, page_num: int) -> Optional[bytes]:
    """Render a high-resolution PNG image of a PDF page."""
    try:
        _check_file(file_path)
        doc = fitz.open(file_path)
        if page_num < 0 or page_num >= len(doc): return None
        page = doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_bytes = pix.tobytes("png")
        doc.close()
        return img_bytes
    except Exception as e:
        logging.error(f"Error rendering page image: {e}")
        return None

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


def _map_font_name(font_name: str) -> str:
    """Map arbitrary PDF font names to standard Base 14 names for insert_text."""
    if not font_name:
        return "Helvetica"
        
    fn = font_name.lower()
    
    # Check for Bold/Italic keywords
    is_bold = "bold" in fn
    is_italic = "italic" in fn or "oblique" in fn
    
    # Map to standard families
    family = "Helvetica" # Default
    if "times" in fn or "roman" in fn:
        family = "Times-Roman"
        if is_bold and is_italic: return "Times-BoldItalic"
        if is_bold: return "Times-Bold"
        if is_italic: return "Times-Italic"
        return "Times-Roman"
    elif "courier" in fn or "mono" in fn:
        family = "Courier"
        if is_bold and is_italic: return "Courier-BoldOblique"
        if is_bold: return "Courier-Bold"
        if is_italic: return "Courier-Oblique"
        return "Courier"
    else:
        family = "Helvetica"
        if is_bold and is_italic: return "Helvetica-BoldOblique"
        if is_bold: return "Helvetica-Bold"
        if is_italic: return "Helvetica-Oblique"
        return "Helvetica"

# ================= TEXT REPLACEMENT =================
def add_text_replacement(
    input_path: str,
    output_path: str,
    replacements: Dict[str, str],
    font_name: Optional[str] = None,
    font_size: Optional[float] = None,
    color: Optional[tuple] = None,
    page_num: Optional[int] = None  # None = all pages, int = specific page only
) -> bool:
    """
    Replace text in PDF with intelligent style inheritance.
    page_num: 0-based page index. If set, only that page is modified.
    """
    try:
        _check_file(input_path)
        doc = fitz.open(input_path)

        # Determine which pages to process
        pages_to_process = [doc[page_num]] if page_num is not None and 0 <= page_num < len(doc) else list(doc)

        for page in pages_to_process:
            page_dict = None # Lazy load page dict for speed
            
            for old_text, new_text in replacements.items():
                areas = page.search_for(old_text)
                if not areas:
                    continue

                # FOR STYLE INHERITANCE
                current_size = font_size
                current_font = font_name
                current_color = color
                
                if current_size is None or current_font is None or current_color is None:
                    if page_dict is None:
                        page_dict = page.get_text("dict")
                    
                    found_style = False
                    first_rect = areas[0]
                    for block in page_dict.get("blocks", []):
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                if old_text in span["text"]:
                                    span_rect = fitz.Rect(span["bbox"])
                                    if span_rect.intersects(first_rect):
                                        if current_size is None: current_size = span["size"]
                                        if current_font is None: current_font = span["font"]
                                        if current_color is None: 
                                            c = span["color"]
                                            current_color = (
                                                ((c >> 16) & 0xFF) / 255.0,
                                                ((c >> 8) & 0xFF) / 255.0,
                                                (c & 0xFF) / 255.0
                                            )
                                        found_style = True
                                        break
                            if found_style: break
                        if found_style: break

                # FALLBACKS & Normalization
                if current_size is None: current_size = 11
                if current_color is None: current_color = (0, 0, 0)
                
                # FONT SAFETY: Map font name to standard if possible
                standard_font = _map_font_name(current_font)

                for rect in areas:
                    page.add_redact_annot(rect, fill=None)
                page.apply_redactions()
                
                for rect in areas:
                    try:
                        # Try the detected font first
                        page.insert_text(
                            rect.top_left + (0, current_size * 0.8),
                            new_text,
                            fontname=current_font if current_font else standard_font,
                            fontsize=current_size,
                            color=current_color
                        )
                    except Exception as e:
                        # FALLBACK if font fails (e.g. "need font file or buffer")
                        logging.warning(f"Font insertion failed for '{current_font}', falling back to '{standard_font}': {e}")
                        try:
                            page.insert_text(
                                rect.top_left + (0, current_size * 0.8),
                                new_text,
                                fontname=standard_font,
                                fontsize=current_size,
                                color=current_color
                            )
                        except Exception as e2:
                            logging.error(f"Ultimate font fallback failed: {e2}")
                            # Last resort: absolute standard
                            page.insert_text(
                                rect.top_left + (0, current_size * 0.8),
                                new_text,
                                fontname="Helvetica",
                                fontsize=current_size,
                                color=current_color
                            )

        # Handle same-file save crash
        if input_path == output_path:
            temp_path = output_path + ".tmp"
            doc.save(temp_path)
            doc.close()
            os.replace(temp_path, output_path)
        else:
            doc.save(output_path)
            doc.close()
        return True
    except Exception as e:
        import traceback
        logging.error(f"❌ Error replacing text: {e}\n{traceback.format_exc()}")
        return False

# ================= IMAGE REPLACEMENT =================
def add_image_replacement(
    input_path: str,
    output_path: str,
    replacements: Dict[str, str],
) -> bool:
    """
    Replace text placeholders with images.
    replacements maps 'old_text' -> base64 image string.
    """
    import base64
    try:
        _check_file(input_path)
        doc = fitz.open(input_path)

        for page in doc:
            for old_text, b64_img in replacements.items():
                if not old_text or not b64_img:
                    continue
                areas = page.search_for(old_text)
                if not areas:
                    continue
                
                img_bytes = base64.b64decode(b64_img)
                
                # Redact the old text to remove the placeholder
                for rect in areas:
                    page.add_redact_annot(rect, fill=None)
                page.apply_redactions()

                # Insert the image at the location of the text
                for rect in areas:
                    # Adjust rect slightly to make signature look natural
                    img_rect = fitz.Rect(rect.x0, rect.y0 - 15, rect.x1, rect.y1 + 10)
                    try:
                        page.insert_image(img_rect, stream=img_bytes, keep_proportion=True)
                    except Exception as e:
                        logging.error(f"Failed to insert image: {e}")

        # Handle same-file save crash
        if input_path == output_path:
            temp_path = output_path + ".tmp"
            doc.save(temp_path)
            doc.close()
            os.replace(temp_path, output_path)
        else:
            doc.save(output_path)
            doc.close()
        return True
    except Exception as e:
        import traceback
        logging.error(f"❌ Error replacing text with image: {e}\n{traceback.format_exc()}")
        return False
def add_coordinate_form_fills(
    input_path: str,
    output_path: str,
    text_values: Dict[str, str],
    image_values: Dict[str, str] = None,
) -> bool:
    """
    Fill visual form blanks by coordinates.

    Keys are JSON strings containing {"page": int, "rect": [x0, y0, x1, y1]}.
    Text is placed just above the underline; images are fit over the target area.
    """
    import base64
    import json

    image_values = image_values or {}
    try:
        _check_file(input_path)
        doc = fitz.open(input_path)

        def parse_target(raw_key: str):
            try:
                target = json.loads(raw_key)
                page_no = int(target.get("page", 0))
                rect_values = target.get("rect") or []
                if len(rect_values) != 4 or page_no < 0 or page_no >= len(doc):
                    return None, None
                return doc[page_no], fitz.Rect(rect_values)
            except Exception:
                return None, None

        for raw_key, value in text_values.items():
            if not value:
                continue
            page, rect = parse_target(raw_key)
            if page is None or rect is None:
                continue
            page.insert_text(
                fitz.Point(rect.x0 + 3, rect.y0 - 3),
                str(value),
                fontname="Helvetica",
                fontsize=11,
                color=(0, 0, 0),
            )

        for raw_key, b64_img in image_values.items():
            if not b64_img:
                continue
            page, rect = parse_target(raw_key)
            if page is None or rect is None:
                continue
            img_bytes = base64.b64decode(b64_img)
            height = max(22, rect.height + 22)
            img_rect = fitz.Rect(rect.x0, rect.y0 - height + 8, rect.x1, rect.y0 + 8)
            page.insert_image(img_rect, stream=img_bytes, keep_proportion=True)

        if input_path == output_path:
            temp_path = output_path + ".tmp"
            doc.save(temp_path)
            doc.close()
            os.replace(temp_path, output_path)
        else:
            doc.save(output_path)
            doc.close()
        return True
    except Exception as e:
        import traceback
        logging.error(f"Error filling coordinate fields: {e}\n{traceback.format_exc()}")
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
    Add a diagonal grey text watermark to every page.
    Uses insert_text with a rotation morph — works on PyMuPDF 1.18+.
    """
    try:
        doc = fitz.open(input_path)

        for page in doc:
            pw = page.rect.width
            ph = page.rect.height
            cx = pw / 2
            cy = ph / 2

            # Rotation matrix 45° around the page centre
            pivot = fitz.Point(cx, cy)
            mat   = fitz.Matrix(45)          # 45-degree rotation

            # Start point: offset left so the rotated text centres nicely
            start = fitz.Point(cx - len(text) * 14, cy)

            page.insert_text(
                start,
                text,
                fontsize=52,
                fontname="helv",
                color=(0.65, 0.65, 0.65),
                morph=(pivot, mat),
            )

        if input_path == output_path:
            tmp = output_path + ".tmp"
            doc.save(tmp)
            doc.close()
            os.replace(tmp, output_path)
        else:
            doc.save(output_path)
            doc.close()
        return True

    except Exception as e:
        logging.error(f"❌ Error adding watermark: {e}")
        import traceback
        logging.error(traceback.format_exc())
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
            text = highlight.get("text", "")
            color = highlight.get("color", (1, 1, 0))  # Yellow default
            page_num = highlight.get("page", -1)

            # page=-1 means search all pages (used by the API endpoint)
            pages_to_search = range(len(doc)) if page_num < 0 else [page_num]

            for pn in pages_to_search:
                if pn >= len(doc):
                    continue
                page = doc[pn]
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

def fill_form_pdf(input_path: str, output_path: str, field_values: Dict[str, str], image_values: Dict[str, str] = None) -> bool:
    """
    Fill form fields in PDF and optionally paste images (e.g. signatures) over fields.
    
    Args:
        input_path: Path to PDF form
        output_path: Path to save filled PDF
        field_values: Dict mapping field_name -> value
        image_values: Dict mapping field_name -> base64 image
    
    Returns:
        bool: Success status
    """
    import base64
    try:
        doc = fitz.open(input_path)
        image_values = image_values or {}

        for page in doc:
            widgets = page.widgets() or []
            for widget in widgets:
                if widget.field_name in field_values:
                    widget.field_value = field_values[widget.field_name]
                    widget.update()
                if widget.field_name in image_values and image_values[widget.field_name]:
                    try:
                        img_bytes = base64.b64decode(image_values[widget.field_name])
                        page.insert_image(widget.rect, stream=img_bytes, keep_proportion=True)
                    except Exception as e:
                        logging.error(f"Failed to insert image into widget {widget.field_name}: {e}")

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


# ================= SECURITY & PERMISSIONS =================
def set_pdf_security(input_path: str, output_path: str, user_pw: str = "", owner_pw: str = "", permissions: int = -1) -> bool:
    """
    Encrypt PDF and set permissions.
    
    Args:
        input_path: Path to original PDF
        output_path: Path to save secured PDF
        user_pw: Password for opening
        owner_pw: Password for editing
        permissions: Integer bitmask for permissions
    
    Returns:
        bool: Success status
    """
    try:
        doc = fitz.open(input_path)
        # Use user_pw for user access, owner_pw for full access
        # If no owner_pw, use user_pw
        opw = owner_pw if owner_pw else user_pw
        
        doc.save(
            output_path,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw=opw,
            user_pw=user_pw,
            permissions=permissions
        )
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error setting security: {e}")
        return False


# ================= PAGE NUMBERS =================
def add_page_numbers(input_path: str, output_path: str, position: str = "bottom_right") -> bool:
    """
    Add page numbers to all pages.
    """
    try:
        doc = fitz.open(input_path)
        total_pages = len(doc)
        
        for i, page in enumerate(doc):
            text = f"Page {i+1} of {total_pages}"
            if position == "bottom_right":
                p = (page.rect.width - 100, page.rect.height - 30)
            elif position == "bottom_center":
                p = (page.rect.width / 2 - 40, page.rect.height - 30)
            else: # bottom_left
                p = (50, page.rect.height - 30)
                
            page.insert_text(p, text, fontsize=10, color=(0.5, 0.5, 0.5))
            
        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error adding page numbers: {e}")
        return False


# ================= BACKGROUND COLOR =================
def set_background_color(input_path: str, output_path: str, color: tuple = (1, 1, 1)) -> bool:
    """
    Set background color for all pages.
    """
    try:
        doc = fitz.open(input_path)
        for page in doc:
            page.draw_rect(page.rect, color=color, fill=color, overlay=False)
            
        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error setting background: {e}")
        return False


# ================= FORM FIELD CREATION =================
def create_form_fields(input_path: str, output_path: str, fields: List[Dict]) -> bool:
    """
    Add interactive form fields to PDF.
    
    Args:
        fields: List of dicts with:
            - page (int)
            - name (str)
            - type (str): 'text', 'checkbox'
            - rect (List[float]): [x1, y1, x2, y2]
    """
    try:
        doc = fitz.open(input_path)
        for f in fields:
            page_num = f.get("page", 0)
            if page_num >= len(doc): continue
            
            page = doc[page_num]
            rect = fitz.Rect(f["rect"])
            
            widget = fitz.Widget()
            widget.rect = rect
            widget.field_name = f["name"]
            
            if f["type"] == "text":
                widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            elif f["type"] == "checkbox":
                widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
                
            page.add_widget(widget)
            
        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error creating forms: {e}")
        return False


# ================= ADD BLANK PAGE =================
def add_blank_page(input_path: str, output_path: str, after_page: int = -1) -> bool:
    """
    Add a blank page to the PDF.
    """
    try:
        doc = fitz.open(input_path)
        doc.new_page(after_page)
        doc.save(output_path)
        doc.close()
        return True
    except Exception as e:
        print(f"❌ Error adding page: {e}")
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
