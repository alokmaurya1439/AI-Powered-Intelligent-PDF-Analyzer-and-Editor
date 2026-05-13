import streamlit as st
import streamlit.components.v1 as components
import sys
import requests
import os
import logging
import base64
from pathlib import Path
import fitz
import io
from PIL import Image



# ================= PATH SETUP =================
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

API_URL = "http://127.0.0.1:8000"
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"

# Create directories if they don't exist
Path(UPLOAD_DIR).mkdir(exist_ok=True)
Path(OUTPUT_DIR).mkdir(exist_ok=True)


# ================= PAGE CONFIG =================
st.set_page_config(
    page_title="AI Powered Intelligent PDF Analyzer and Editor",
    page_icon="✂",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================= SESSION STATE =================
if 'theme' not in st.session_state:
    st.session_state.theme = "Light Mode"
if 'translate_pages' not in st.session_state:
    st.session_state.translate_pages = []

# ================= CUSTOM CSS =================
st.markdown("""
    <style>
    .main {
        padding-top: 0rem;
    }
    .stButton>button {
        width: 100%;
        padding: 0.6rem;
        font-size: 1rem;
    }
    .stTabs [data-baseweb="tab-list"] button {
        font-size: 1.1rem;
    }
    </style>
    """, unsafe_allow_html=True)


# ================= HELPER FUNCTIONS =================
def check_api_health():
    """Check if API is running"""
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        return response.status_code == 200
    except:
        return False


def safe_api_call(endpoint: str, files=None, data=None, method="POST", timeout=None):
    try:
        formatted_files = None
        if files:
            formatted_files = {}
            for key, value in files.items():
                if isinstance(value, tuple):
                    formatted_files[key] = value
                elif hasattr(value, "read") and hasattr(value, "name"):
                    value.seek(0)
                    fname = value.name.lower()
                    if fname.endswith((".png",)):
                        mime = "image/png"
                    elif fname.endswith((".jpg", ".jpeg")):
                        mime = "image/jpeg"
                    elif fname.endswith(".gif"):
                        mime = "image/gif"
                    else:
                        mime = "application/pdf"
                    formatted_files[key] = (value.name, value, mime)
                elif isinstance(value, (bytes, bytearray)):
                    formatted_files[key] = (f"{key}.pdf", value, "application/pdf")
                else:
                    formatted_files[key] = value

        if method == "POST":
            request_timeout = timeout if timeout is not None else 600
            response = requests.post(
                f"{API_URL}{endpoint}",
                files=formatted_files,
                data=data,
                timeout=request_timeout
            )
        else:
            response = requests.get(
                f"{API_URL}{endpoint}",
                timeout=30
            )

        # 🔥 DEBUG (VERY IMPORTANT)
        print("STATUS:", response.status_code)
        print("RESPONSE:", response.text[:500])

        # ✅ Check if response is JSON
        content_type = response.headers.get("content-type", "")

        if response.status_code == 200:
            if "application/json" in content_type:
                return True, response
            else:
                # ⚠️ Not JSON (PDF / text / error)
                return True, response
        else:
            return False, response.text

    except requests.exceptions.ConnectionError:
        return False, "❌ API Server is not running."
    except requests.exceptions.Timeout:
        return False, "⏱️ Request timed out."
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

def display_error(message: str):
    """Display error message"""
    st.error(message)


def display_success(message: str):
    """Display success message"""
    st.success(message)


def render_image_with_text(img_bytes: bytes, text: str) -> bytes:
    """
    Draw extracted text as a semi-transparent banner overlaid at the
    bottom of the image. Returns PNG bytes of the composite image.
    """
    from PIL import Image as _Image, ImageDraw as _Draw, ImageFont as _Font
    import io as _io

    img = _Image.open(_io.BytesIO(img_bytes)).convert("RGBA")
    w, h = img.size

    # Banner height = ~22% of image height, min 40px
    banner_h = max(40, int(h * 0.22))
    font_size = max(16, int(banner_h * 0.45))

    # Semi-transparent dark green overlay
    overlay = _Image.new("RGBA", (w, banner_h), (20, 60, 20, 210))
    img.paste(overlay, (0, h - banner_h), overlay)

    draw = _Draw.Draw(img)

    # Try to load a system font, fall back to default
    font = None
    for fp in [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]:
        try:
            font = _Font.truetype(fp, font_size)
            break
        except Exception:
            pass
    if font is None:
        font = _Font.load_default()

    label = f"📝 {text}"
    # Truncate if too long
    max_chars = max(10, int(w / (font_size * 0.6)))
    if len(label) > max_chars:
        label = label[:max_chars - 1] + "…"

    # Draw text with a subtle shadow then white text
    tx, ty = 10, h - banner_h + (banner_h - font_size) // 2
    draw.text((tx + 1, ty + 1), label, font=font, fill=(0, 0, 0, 180))
    draw.text((tx, ty), label, font=font, fill=(180, 255, 180, 255))

    out = _io.BytesIO()
    img.convert("RGB").save(out, format="PNG")
    return out.getvalue()


def display_pdf_preview(pdf_bytes: bytes, height: int = 700):
    """Display embedded PDF preview with download and browser-safe open/download support."""
    if not pdf_bytes:
        st.warning("PDF preview unavailable.")
        return

    base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
    pdf_data_url = f"data:application/pdf;base64,{base64_pdf}"

    html = f"""
        <div style='display:flex; justify-content:flex-end; gap:10px; margin-bottom:10px; flex-wrap:wrap;'>
            <a href='{pdf_data_url}' target='_blank' rel='noopener noreferrer' style='padding:0.6rem 1rem; font-size:1rem; cursor:pointer; background:#1976d2; color:#fff; text-decoration:none; border-radius:6px;'>📄 Open Full PDF</a>
            <a href='{pdf_data_url}' download='preview.pdf' style='padding:0.6rem 1rem; font-size:1rem; cursor:pointer; background:#4caf50; color:#fff; text-decoration:none; border-radius:6px;'>⬇️ Download PDF</a>
        </div>
        <iframe id='pdfFrame' src='{pdf_data_url}' width='100%' height='{height}px' style='border:1px solid #ccc;' allowfullscreen></iframe>
    """
    components.html(html, height=height + 100, scrolling=True)
    st.caption("If the embedded preview does not render, use the Open Full PDF button above.")


# ================= UI SETUP =================
st.title("🤖 AI Powered Intelligent PDF Analyzer and Editor")


# ============ Sidebar ===============
with st.sidebar:
    col1, col2 = st.columns([6, 6])

    with col1:
        try:
            st.image("image/1000210001.png", width=150)
        except:
            st.warning("Logo not found")

    with col2:
        st.markdown("## 🏠 Home")

    st.divider()

    # Theme Selection
    st.session_state.theme = st.radio(
        "🎨 Choose Theme",
        ["Light Mode", "Dark Mode"],
        index=0 if st.session_state.theme == "Light Mode" else 1,
        horizontal=True
    )

    st.divider()

    # API Status
    api_status = check_api_health()
    if api_status:
        st.success("✅ API Status: Online")
    else:
        st.error("❌ API Status: Offline")
        st.info("Please start the backend server to use features.")

    st.divider()


# ================= THEME APPLICATION =================
if st.session_state.theme == "Dark Mode":
    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] {
        background-color: #0e1117 !important;
        color: #fafafa !important;
    }
    [data-testid="stSidebar"] {
        background-color: #262730 !important;
        color: #fafafa !important;
    }
    [data-testid="stHeader"] {
        background-color: #262730 !important;
    }
    .stTextInput>div>div>input, .stTextArea>div>textarea, .stSelectbox>div>div>select {
        background-color: #262730 !important;
        color: #fafafa !important;
        border-color: #4a4a4a !important;
    }
    .stRadio>div {
        color: #fafafa !important;
    }
    .stButton>button {
        background-color: #4CAF50 !important;
        color: white !important;
    }
    .stSuccess, .stInfo, .stWarning, .stError {
        color: #fafafa !important;
    }
    .stMarkdown, .stText {
        color: #fafafa !important;
    }
    </style>
    """, unsafe_allow_html=True)


# ================= TOOLS MENU =================
menu = st.sidebar.selectbox(
    "⚡ Choose Action",
     [
        "📌 Tools Dashboard",
        "⚠️ Detect Errors",
        "✂ PDF Edit",
        "✍ Improve Writing",
        "🧹 Fix Formatting",
        "📄 Smart Form Filling",
        "🔄 Convert Other Files to PDF",
        "🔄 Convert PDF to Other Files",
        "🤖 Summarize PDF",
        "🌍 Translate PDF"
    ]
)


# ================= HOME/DASHBOARD =================
if menu == "📌 Tools Dashboard":
    st.header("📌 AI PDF Tools Dashboard")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("PDF Tools", "9", "+")
        st.metric("Features", "20+", "✓")
    
    with col2:
        st.metric("Supported Languages", "6", "🌍")
        st.metric("Max File Size", "100MB", "📦")
    
    with col3:
        st.metric("Processing Speed", "Fast", "⚡")
        st.metric("Accuracy", "95%+", "🎯")
    
    st.divider()
    
    st.write("""
    ### 🎯 Available Features:
    
    1. **⚠️ Detect Errors** - Find & fix errors in PDFs
    2. **✂ PDF Edit** - Edit text, images, and layouts
    3. **✍ Improve Writing** - Enhance content quality
    4. **🧹 Fix Formatting** - Normalize document format
    5. **📄 Smart Form Filling** - Auto-detect & fill PDF form fields
    6. **🔄 Convert to PDF** - Convert files to PDF format
    7. **🔄 Convert from PDF** - Export to other formats
    8. **🤖 Summarize** - Generate smart summaries
    9. **🌍 Translate** - Multi-language translation
    
    ### 📋 How to Use:
    1. Select a tool from the sidebar
    2. Upload your PDF or file
    3. Configure options as needed
    4. Click the action button to process
    5. Download the result
    """)

# ================= ERROR DETECTION =================
elif menu == "⚠️ Detect Errors":
    st.header("⚠️ PDF Error Detection")
    st.write("Analyze your PDF for errors and get corrections")
    
    if "error_detect_data" not in st.session_state:
        st.session_state.error_detect_data = None
    
    uploaded_file = st.file_uploader(
        "📤 Upload PDF for Error Detection",
        type=["pdf"],
        key="error_detect_upload"
    )
   
    if uploaded_file:
        st.success(f"✅ File uploaded: {uploaded_file.name}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            detection_level = st.selectbox(
                "Detection Level",
                ["Basic", "Intermediate", "Deep Analysis"]
            )
        
        with col2:
            max_pages = st.number_input(
                "Max Pages to Analyze (0 = all)",
                min_value=0, max_value=500, value=0, step=10,
                help="Limit analysis to first N pages. Set 0 to analyze the entire document."
            )
        
        if st.button("🔍 Detect Errors", key="detect_btn"):
            if not api_status:
                display_error("API Server is offline")
            else:
                with st.spinner("🔄 Analyzing PDF..."):
                    success, response = safe_api_call(
                        "/error-detector",
                        files={"file": uploaded_file},
                        data={"detection_level": detection_level, "max_pages": int(max_pages)}
                    )
                
                if success:
                    st.session_state.error_detect_data = response.json()
                    st.session_state.error_detect_file_name = uploaded_file.name
                    st.session_state.error_detect_file_bytes = uploaded_file.getvalue()
                    st.session_state.error_detect_level = detection_level
                    # Clear any previously generated corrected PDF
                    st.session_state.pop("corrected_pdf_bytes", None)
                    st.session_state.pop("corrected_pdf_text", None)
                    st.session_state.pop("corrected_pdf_name", None)
                    display_success("✅ Analysis complete!")
                else:
                    display_error(response)
    
    # Display Results
    if st.session_state.error_detect_data:
        st.divider()
        st.subheader("📊 Results")

        # Show which detection level was used
        _used_level = st.session_state.get("error_detect_level", "Basic")
        _level_color = {"Basic": "#4caf50", "Intermediate": "#ff9800", "Deep Analysis": "#f44336"}
        _lc = _level_color.get(_used_level, "#4caf50")
        st.markdown(
            f"<span style='background:{_lc};color:#fff;padding:3px 12px;"
            f"border-radius:12px;font-size:0.82rem;font-weight:700;'>"
            f"🔍 Detection Level: {_used_level}</span>",
            unsafe_allow_html=True,
        )
        st.markdown("")

        data = st.session_state.error_detect_data
        
        tabs = st.tabs(["📄 View PDF", "📝 Text", "📊 Metadata", "⭐ Quality", "🧠 Errors", "📥 Download"])
        
        with tabs[0]:
            if "error_detect_file_bytes" in st.session_state:
                try:
                    doc = fitz.open(stream=st.session_state.error_detect_file_bytes, filetype="pdf")
                    errors_raw = data.get("errors", "")

                    # ── Parse error blocks ────────────────────────────────
                    def _parse_error_blocks(raw: str):
                        blocks, current = [], {}
                        for line in raw.splitlines():
                            s = line.strip()
                            if s.lower().startswith("error:"):
                                if current.get("error"):
                                    blocks.append(current)
                                current = {"error": s[6:].strip(), "correction": "", "explanation": ""}
                            elif s.lower().startswith("correction:") and current:
                                current["correction"] = s[11:].strip()
                            elif s.lower().startswith("explanation:") and current:
                                current["explanation"] = s[12:].strip()
                        if current.get("error"):
                            blocks.append(current)
                        return blocks

                    error_blocks = _parse_error_blocks(errors_raw)

                    # ── Extract just the bare error word/phrase ───────────
                    def _bare(s: str) -> str:
                        return s.strip().strip('"\'').strip()

                    # ── Only underline genuine misspellings ───────────────
                    # A block is underline-worthy only if:
                    #   1. error word != correction word (it's actually wrong)
                    #   2. error word is short (1-2 words) — long phrases match too broadly
                    #   3. error and correction differ by more than just capitalisation
                    def _is_underlineable(block: dict) -> bool:
                        err  = _bare(block.get("error", "")).lower()
                        corr = _bare(block.get("correction", "")).lower()
                        if not err:
                            return False
                        # Same word → style note, not a spelling error
                        if err == corr:
                            return False
                        # Only capitalisation differs → not a spelling error
                        if err.lower() == corr.lower():
                            return False
                        # Long phrase → matches too many places
                        if len(err.split()) > 2:
                            return False
                        # Error word is too short to be meaningful (single char)
                        if len(err) < 3:
                            return False
                        # Correction is just the error with different capitalisation
                        if err.replace(" ", "") == corr.replace(" ", ""):
                            return False
                        return True

                    # Only keep blocks worth underlining
                    underline_blocks = [b for b in error_blocks if _is_underlineable(b)]

                    st.write(f"**Total Pages:** {len(doc)}")

                    for page_num in range(len(doc)):
                        page = doc.load_page(page_num)

                        # Draw red underline ONLY under genuine misspelled words
                        for b in underline_blocks:
                            token = _bare(b["error"])
                            if not token or len(token.split()) > 2:
                                continue
                            hits = page.search_for(token, quads=False)
                            for rect in hits:
                                underline_y = rect.y1 + 1
                                page.draw_line(
                                    fitz.Point(rect.x0, underline_y),
                                    fitz.Point(rect.x1, underline_y),
                                    color=(1, 0, 0),
                                    width=1.5,
                                )

                        # Render page to image after drawing
                        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                        img = Image.open(io.BytesIO(pix.tobytes("png")))
                        st.image(img, caption=f"Page {page_num + 1}", use_container_width=True)

                        # ── Error summary cards below each page ───────────
                        if error_blocks:
                            page_text = (page.get_text() or "").lower()
                            page_errors = [
                                b for b in error_blocks
                                if _bare(b["error"]).lower() in page_text
                            ]
                            if not page_errors and page_num == 0:
                                page_errors = error_blocks

                            if page_errors:
                                st.markdown(
                                    f"<div style='background:#1a1a2e;border-radius:8px;"
                                    f"padding:8px 14px;margin:4px 0 8px 0;'>"
                                    f"<span style='color:#ef9a9a;font-weight:700;font-size:0.9rem;'>"
                                    f"🔍 {len(page_errors)} error(s) on Page {page_num + 1}</span></div>",
                                    unsafe_allow_html=True,
                                )
                                for b in page_errors:
                                    err_val  = b["error"]
                                    corr_val = b["correction"]
                                    expl_val = b["explanation"]
                                    st.markdown(
                                        f"<div style='border:1px solid #f44336;border-radius:8px;"
                                        f"padding:10px 14px;margin:4px 0;background:#2a0a0a;'>"
                                        f"<div style='color:#ff5252;font-weight:700;font-size:0.9rem;'>"
                                        f"🔴 Error: <span style='font-weight:400'>{err_val}</span></div>"
                                        + (
                                            f"<div style='color:#69f0ae;font-weight:600;font-size:0.87rem;"
                                            f"margin-top:4px;'>✅ Correction: "
                                            f"<span style='font-weight:400'>{corr_val}</span></div>"
                                            if corr_val else ""
                                        )
                                        + (
                                            f"<div style='color:#90caf9;font-size:0.83rem;"
                                            f"margin-top:4px;font-style:italic;'>💡 {expl_val}</div>"
                                            if expl_val else ""
                                        )
                                        + "</div>",
                                        unsafe_allow_html=True,
                                    )

                    doc.close()
                except Exception as e:
                    st.error(f"Could not load PDF view: {e}")
            else:
                st.info("PDF file not available for display.")

        with tabs[1]:
            st.text_area(
                "Extracted Text",
                data.get("text", ""),
                height=400,
                disabled=True
            )
        
        with tabs[2]:
            st.text_area(
                "Metadata",
                str(data.get("metadata", {})),
                height=400,
                disabled=True
            )
        
        with tabs[3]:
            quality_data = data.get("quality", {})
            st.text_area(
                "Quality Details",
                str(quality_data),
                height=300,
                disabled=True
            )
        
        with tabs[4]:
            errors = data.get("errors", "")
            # Check if the result genuinely has no errors
            _no_error_signals = [
                "✅ No errors detected",
                "✅ No issues found",
                "✅ No obvious issues",
                "no issues found",
                "no errors found",
                "no errors detected",
            ]
            _is_clean = (
                not errors.strip()
                or (
                    any(sig.lower() in errors.lower() for sig in _no_error_signals)
                    and "•" not in errors
                )
            )
            if _is_clean:
                st.success("✅ No errors detected in this document!")
                st.info("The document appears to be grammatically and structurally correct.")
            else:
                st.warning("⚠️ Issues found in this document:")

                # ── Formatted error renderer ──────────────────────────────
                def _render_errors(raw: str):
                    lines = raw.splitlines()
                    for line in lines:
                        stripped = line.strip()
                        if not stripped:
                            st.markdown("")
                            continue

                        # Section header  e.g. "--- Section 1 (Basic) ---"
                        if stripped.startswith("---") and stripped.endswith("---"):
                            label = stripped.strip("-").strip()
                            st.markdown(
                                f"<div style='background:#1e3a5f;color:#90caf9;"
                                f"padding:6px 14px;border-radius:6px;"
                                f"font-weight:700;font-size:0.95rem;margin:14px 0 6px 0;'>"
                                f"📄 {label}</div>",
                                unsafe_allow_html=True,
                            )

                        # Error line
                        elif stripped.lower().startswith("error:"):
                            val = stripped[6:].strip()
                            st.markdown(
                                f"<div style='background:#4a1010;color:#ff8a80;"
                                f"padding:6px 12px;border-left:4px solid #f44336;"
                                f"border-radius:4px;margin:6px 0 2px 0;"
                                f"font-weight:600;'>🔴 Error: <span style='font-weight:400'>{val}</span></div>",
                                unsafe_allow_html=True,
                            )

                        # Correction line
                        elif stripped.lower().startswith("correction:"):
                            val = stripped[11:].strip()
                            st.markdown(
                                f"<div style='background:#0d3320;color:#69f0ae;"
                                f"padding:6px 12px;border-left:4px solid #00c853;"
                                f"border-radius:4px;margin:2px 0;"
                                f"font-weight:600;'>✅ Correction: <span style='font-weight:400'>{val}</span></div>",
                                unsafe_allow_html=True,
                            )

                        # Explanation line
                        elif stripped.lower().startswith("explanation:"):
                            val = stripped[12:].strip()
                            st.markdown(
                                f"<div style='background:#1a1a2e;color:#b0bec5;"
                                f"padding:6px 12px;border-left:4px solid #7986cb;"
                                f"border-radius:4px;margin:2px 0 8px 0;"
                                f"font-style:italic;'>💡 Explanation: {val}</div>",
                                unsafe_allow_html=True,
                            )

                        # ✅ No issues line
                        elif stripped.startswith("✅"):
                            st.success(stripped)

                        # ℹ️ info / note lines
                        elif stripped.startswith("ℹ️") or stripped.startswith("*(Note"):
                            st.info(stripped.strip("*()"))

                        # Bullet points
                        elif stripped.startswith("•"):
                            st.markdown(f"&nbsp;&nbsp;{stripped}", unsafe_allow_html=True)

                        # Plain text fallback
                        else:
                            st.markdown(
                                f"<p style='color:#cfd8dc;margin:3px 0;font-size:0.9rem;'>{stripped}</p>",
                                unsafe_allow_html=True,
                            )

                _render_errors(errors)
        
        with tabs[5]:
            st.subheader("Generate Corrected PDF")

            if st.button("✨ Generate Corrected PDF", key="corrected_pdf_btn"):
                if not api_status:
                    display_error("API Server is offline")
                else:
                    with st.spinner("⏳ Generating corrected PDF..."):
                        success, response = safe_api_call(
                            "/corrected-pdf",
                            files={
                                "file": (
                                    st.session_state.error_detect_file_name,
                                    st.session_state.error_detect_file_bytes,
                                    "application/pdf",
                                )
                            }
                        )

                    if success:
                        content_type = response.headers.get("content-type", "").lower()
                        is_pdf = "pdf" in content_type or response.content.startswith(b"%PDF")

                        if is_pdf:
                            # Store in session_state so it survives reruns
                            st.session_state["corrected_pdf_bytes"] = response.content
                            st.session_state["corrected_pdf_name"] = os.path.splitext(
                                st.session_state.error_detect_file_name
                            )[0]
                            st.session_state["corrected_pdf_text"] = None
                        else:
                            try:
                                result = response.json()
                                corrected_text = result.get("corrected_text", "")
                                st.session_state["corrected_pdf_bytes"] = None
                                st.session_state["corrected_pdf_text"] = corrected_text
                                st.session_state["corrected_pdf_name"] = os.path.splitext(
                                    st.session_state.get("error_detect_file_name", "document")
                                )[0]
                                if not corrected_text:
                                    st.warning(result.get("message", "PDF generation failed."))
                            except Exception:
                                st.error("Failed to generate PDF and could not parse fallback text.")
                    else:
                        error_msg = response if isinstance(response, str) else "Unknown error"
                        st.error(f"Failed to generate corrected PDF: {error_msg}")

            # ── Always show result if available (persists across reruns) ──
            if st.session_state.get("corrected_pdf_bytes"):
                original_name = st.session_state.get("corrected_pdf_name", "document")
                display_success("✅ Corrected PDF ready!")
                st.download_button(
                    label="⬇️ Download Corrected PDF",
                    data=st.session_state["corrected_pdf_bytes"],
                    file_name=f"{original_name}_corrected.pdf",
                    mime="application/pdf",
                    key="dl_corrected_pdf"
                )

            elif st.session_state.get("corrected_pdf_text"):
                corrected_text = st.session_state["corrected_pdf_text"]
                original_name  = st.session_state.get("corrected_pdf_name", "document")
                st.text_area("Corrected Text", corrected_text, height=300)
                col_dl1, col_dl2 = st.columns(2)
                with col_dl1:
                    st.download_button(
                        label="⬇️ Download as Text (.txt)",
                        data=corrected_text,
                        file_name=f"{original_name}_corrected.txt",
                        mime="text/plain",
                        key="dl_corrected_txt"
                    )
                with col_dl2:
                    try:
                        from fpdf import FPDF
                        _pdf = FPDF(unit="pt", format="letter")
                        _pdf.set_auto_page_break(auto=True, margin=40)
                        _pdf.add_page()
                        _pdf.set_font("Helvetica", size=11)
                        for _line in corrected_text.splitlines():
                            safe = _line.encode("latin-1", "replace").decode("latin-1")
                            if safe.strip():
                                _pdf.multi_cell(0, 16, text=safe)
                            else:
                                _pdf.ln(8)
                        _pdf_bytes = bytes(_pdf.output())
                        st.download_button(
                            label="⬇️ Download as PDF",
                            data=_pdf_bytes,
                            file_name=f"{original_name}_corrected.pdf",
                            mime="application/pdf",
                            key="dl_corrected_pdf_fallback"
                        )
                    except Exception as _e:
                        st.info(f"PDF download unavailable: {_e}")

# ================= PDF EDIT =================
elif menu == "✂ PDF Edit":
    st.header("✂ PDF Editing Tool")
    st.write("Edit text, images, and structure of your PDFs")
    
    uploaded_file = st.file_uploader(
        "📤 Upload PDF to Edit",
        type=["pdf"],
        key="pdf_edit_upload"
    )
    
    if uploaded_file:
        st.success(f"✅ File uploaded: {uploaded_file.name}")
        
        # Session state to track the "Live" PDF being edited and Undo History
        if "edit_pdf_bytes" not in st.session_state or st.session_state.edit_pdf_name != uploaded_file.name:
            st.session_state.edit_pdf_bytes = uploaded_file.getvalue()
            st.session_state.edit_pdf_name = uploaded_file.name
            st.session_state.edit_pdf_history = [uploaded_file.getvalue()]

        # Define a helper to update the live PDF and save to history
        def update_live_pdf(new_bytes, success_msg="✅ PDF Updated!"):
            st.session_state.edit_pdf_history.append(new_bytes)
            # Keep history to a reasonable size
            if len(st.session_state.edit_pdf_history) > 10:
                st.session_state.edit_pdf_history.pop(0)
            st.session_state.edit_pdf_bytes = new_bytes
            st.success(success_msg)
            st.rerun()

        # --- TOOLBOX TABS (MAIN AREA) ---
        st.subheader("🛠️ Professional PDF Toolbox")
        
        # Undo / Reset Buttons
        col_hist_1, col_hist_2, col_hist_3 = st.columns([1, 1, 4])
        with col_hist_1:
            if st.button("⬅️ Undo", disabled=len(st.session_state.get("edit_pdf_history", [])) <= 1):
                st.session_state.edit_pdf_history.pop()
                st.session_state.edit_pdf_bytes = st.session_state.edit_pdf_history[-1]
                st.rerun()
        with col_hist_2:
            if st.button("🔄 Reset"):
                st.session_state.edit_pdf_history = [uploaded_file.getvalue()]
                st.session_state.edit_pdf_bytes = uploaded_file.getvalue()
                st.rerun()

        with st.expander("👁️ View Full Live Document — Inline Text Editor", expanded=True):
            try:
                doc = fitz.open(stream=st.session_state.edit_pdf_bytes, filetype="pdf")
                total_pages = len(doc)

                # ── Page selector ──────────────────────────────────────
                st.caption(f"📄 {total_pages} page(s) — select a page, click a line to edit it.")
                edit_page = st.number_input(
                    "Page", min_value=1, max_value=total_pages, value=1, step=1,
                    key="live_doc_page"
                ) - 1  # 0-based

                page = doc.load_page(edit_page)

                # ── Render page image ───────────────────────────────────
                pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                st.image(
                    Image.open(io.BytesIO(pix.tobytes("png"))),
                    caption=f"Page {edit_page + 1} of {total_pages}",
                    use_container_width=True
                )

                # ── Extract unique text lines for this page ─────────────
                page_dict = page.get_text("dict")
                lines_seen = set()
                ordered_lines = []
                for block in page_dict.get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        line_text = " ".join(
                            sp.get("text", "").strip()
                            for sp in line.get("spans", [])
                            if sp.get("text", "").strip()
                        )
                        if not line_text or line_text in lines_seen:
                            continue
                        size = line["spans"][0].get("size", 11) if line.get("spans") else 11
                        lines_seen.add(line_text)
                        ordered_lines.append({"text": line_text, "size": size})

                doc.close()

                if not ordered_lines:
                    st.info("No selectable text found on this page (may be a scanned/image page).")
                else:
                    st.markdown(f"**✏️ Page {edit_page + 1} — click a line to select it for editing:**")

                    # ── Line selector buttons ───────────────────────────
                    for li, line in enumerate(ordered_lines):
                        col_line, col_sel = st.columns([6, 1])
                        with col_line:
                            # Highlight selected line
                            is_selected = st.session_state.get("live_selected_line") == f"{edit_page}_{li}"
                            style = "background:#fffde7;padding:4px 8px;border-radius:4px;border-left:3px solid #f9a825;" if is_selected else "padding:4px 8px;"
                            st.markdown(f"<div style='{style}'><small>{line['text']}</small></div>", unsafe_allow_html=True)
                        with col_sel:
                            if st.button("✏️", key=f"sel_{edit_page}_{li}", help="Select this line to edit"):
                                st.session_state.live_selected_line = f"{edit_page}_{li}"
                                st.session_state.live_selected_text = line["text"]
                                st.session_state.live_selected_size = line["size"]
                                st.rerun()

                    st.divider()

                    # ── Edit panel for selected line ────────────────────
                    sel_key = st.session_state.get("live_selected_line", "")
                    sel_text = st.session_state.get("live_selected_text", "")

                    if sel_key and sel_key.startswith(f"{edit_page}_") and sel_text:
                        st.markdown("#### ✏️ Edit Selected Line")
                        st.info(f"**Original:** {sel_text}")

                        new_val = st.text_area(
                            "New text (use Enter/↵ to split into multiple lines)",
                            value=sel_text,
                            height=100,
                            key=f"edit_area_{sel_key}",
                            help="You can press Enter to break this into multiple lines in the PDF"
                        )

                        col_apply, col_del, col_cancel = st.columns([2, 2, 2])
                        with col_apply:
                            if st.button("✅ Apply Change", use_container_width=True, key="live_apply_btn"):
                                if new_val.strip() != sel_text.strip():
                                    lines_to_insert = [l for l in new_val.splitlines() if l.strip()]
                                    replacement = "\n".join(lines_to_insert) if lines_to_insert else " "
                                    with st.spinner("Updating PDF…"):
                                        ok, resp = safe_api_call(
                                            "/replace-text",
                                            files={"file": ("edit.pdf",
                                                            st.session_state.edit_pdf_bytes,
                                                            "application/pdf")},
                                            data={
                                                "old_text": sel_text,
                                                "new_text": replacement,
                                                "page_num": edit_page  # only change THIS page
                                            }
                                        )
                                    if ok:
                                        st.session_state.live_selected_line = ""
                                        st.session_state.live_selected_text = ""
                                        update_live_pdf(resp.content, f"✅ Line updated!")
                                    else:
                                        display_error(resp)
                                else:
                                    st.info("No change detected.")

                        with col_del:
                            if st.button("🗑️ Delete Line", use_container_width=True, key="live_delete_btn"):
                                with st.spinner("Removing line…"):
                                    ok, resp = safe_api_call(
                                        "/replace-text",
                                        files={"file": ("edit.pdf",
                                                        st.session_state.edit_pdf_bytes,
                                                        "application/pdf")},
                                        data={
                                            "old_text": sel_text,
                                            "new_text": " ",
                                            "page_num": edit_page  # only delete from THIS page
                                        }
                                    )
                                if ok:
                                    st.session_state.live_selected_line = ""
                                    st.session_state.live_selected_text = ""
                                    update_live_pdf(resp.content, "✅ Line deleted!")
                                else:
                                    display_error(resp)

                        with col_cancel:
                            if st.button("✖ Cancel", use_container_width=True, key="live_cancel_btn"):
                                st.session_state.live_selected_line = ""
                                st.session_state.live_selected_text = ""
                                st.rerun()
                    else:
                        st.caption("👆 Click ✏️ next to any line above to select it for editing.")

            except Exception as e:
                st.error(f"Could not render Live Document: {e}")
        
        st.divider()

        tabs = st.tabs([
            "📦 Content & Design",
            "🖼️ Media & Branding",
            "📑 Structure",
            "✍️ Annotate",
            "🔏 Security & Sign",
            "🖊️ Forms"
        ])

        with tabs[0]: # Content & Design
            st.markdown("### 🎨 Aesthetics & Layout")
            c3, c4 = st.columns(2)
            with c3:
                st.markdown("#### Background")
                bg_color = st.color_picker("Pick Page Background", "#FFFFFF")
                if st.button("Apply Fill Color"):
                    r, g, b = [int(bg_color[i:i+2], 16)/255.0 for i in (1, 3, 5)]
                    with st.spinner("Applying..."):
                        success, response = safe_api_call("/set-background",
                            files={"file": ("edit.pdf", st.session_state.edit_pdf_bytes, "application/pdf")},
                            data={"r": r, "g": g, "b": b})
                        if success: update_live_pdf(response.content)
                        else: display_error(response)
            with c4:
                st.markdown("#### Page Setup")
                p_pos = st.selectbox("Page Number Position", ["bottom_right", "bottom_center", "bottom_left"])
                if st.button("Number Pages"):
                    with st.spinner("Adding page numbers..."):
                        success, response = safe_api_call("/add-page-numbers",
                            files={"file": ("edit.pdf", st.session_state.edit_pdf_bytes, "application/pdf")},
                            data={"position": p_pos})
                        if success: update_live_pdf(response.content)
                        else: display_error(response)


        with tabs[1]: # Media & Branding
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### Insert Image")
                img_f = st.file_uploader("Choose Image", type=["png", "jpg", "jpeg"], key="img_up")
                pg = st.number_input("Page Number", min_value=1, value=1, key="img_pg")
                col_i1, col_i2 = st.columns(2)
                with col_i1:
                    x = st.number_input("X Pos", value=50.0)
                    w = st.number_input("Width", value=150.0)
                with col_i2:
                    y = st.number_input("Y Pos", value=50.0)
                    h = st.number_input("Height", value=150.0)
                if st.button("📸 Insert Image"):
                    if not img_f: st.warning("Upload an image")
                    else:
                        with st.spinner("Inserting..."):
                            success, response = safe_api_call("/add-image",
                                files={"file": ("edit.pdf", st.session_state.edit_pdf_bytes, "application/pdf"), "image": img_f},
                                data={"page_num": pg, "x": x, "y": y, "width": w, "height": h})
                            if success: update_live_pdf(response.content)
                            else: display_error(response)
            with c2:
                st.markdown("#### Watermarking")
                wm_t = st.text_input("Watermark Text", value="CONFIDENTIAL")
                if st.button("🌊 Apply Watermark"):
                    with st.spinner("Applying..."):
                        success, response = safe_api_call("/add-watermark",
                            files={"file": ("edit.pdf", st.session_state.edit_pdf_bytes, "application/pdf")},
                            data={"watermark_text": wm_t})
                        if success: update_live_pdf(response.content)
                        else: display_error(response)

        with tabs[2]: # Structure
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### Modify Layout")
                rot = st.selectbox("Rotation", [0, 90, 180, 270])
                if st.button("🔄 Rotate All"):
                    with st.spinner("Rotating..."):
                        success, response = safe_api_call("/rotate-pages",
                            files={"file": ("edit.pdf", st.session_state.edit_pdf_bytes, "application/pdf")},
                            data={"angle": rot})
                        if success: update_live_pdf(response.content)
                        else: display_error(response)
                
                st.divider()
                del_pgs = st.text_input("Delete Pages (e.g. 1, 3-5)")
                if st.button("🗑️ Delete Selected Pages"):
                    with st.spinner("Deleting..."):
                        success, response = safe_api_call("/delete-pages",
                            files={"file": ("edit.pdf", st.session_state.edit_pdf_bytes, "application/pdf")},
                            data={"pages": del_pgs})
                        if success: update_live_pdf(response.content)
                        else: display_error(response)
            with c2:
                st.markdown("#### Organize & Combine")

                m_files = st.file_uploader("Merge additional PDFs", type=["pdf"], accept_multiple_files=True)

                # How many pages does the current PDF have?
                try:
                    _cur_doc   = fitz.open(stream=st.session_state.edit_pdf_bytes, filetype="pdf")
                    _cur_pages = len(_cur_doc)
                    _cur_doc.close()
                except Exception:
                    _cur_pages = 1

                merge_after = st.number_input(
                    "Insert merged PDF after page",
                    min_value=0,
                    max_value=_cur_pages,
                    value=_cur_pages,
                    step=1,
                    help=f"0 = insert at beginning, {_cur_pages} = append at end. Current PDF has {_cur_pages} page(s).",
                    key="merge_after_page"
                )
                st.caption(f"📄 Current PDF: {_cur_pages} page(s) — merged PDF will be inserted after page {merge_after}")

                if st.button("🔗 Merge Now"):
                    if not m_files:
                        st.warning("Upload at least one PDF to merge.")
                    else:
                        with st.spinner("Merging..."):
                            files_p = [("files", ("base.pdf", st.session_state.edit_pdf_bytes, "application/pdf"))]
                            for f in m_files:
                                f.seek(0)
                                files_p.append(("files", (f.name, f, "application/pdf")))
                            res = requests.post(
                                f"{API_URL}/merge-pdfs",
                                files=files_p,
                                data={"insert_after": int(merge_after)}
                            )
                            if res.status_code == 200:
                                update_live_pdf(res.content)
                            else:
                                display_error(res.text)

                st.divider()

                blank_after = st.number_input(
                    "Add blank page after page",
                    min_value=0,
                    max_value=_cur_pages,
                    value=_cur_pages,
                    step=1,
                    help=f"0 = insert at beginning, {_cur_pages} = add at end.",
                    key="blank_after_page"
                )
                st.caption(f"Blank page will be inserted after page {blank_after}")

                if st.button("➕ Add Blank Page"):
                    with st.spinner("Adding blank page..."):
                        success, response = safe_api_call(
                            "/add-blank-page",
                            files={"file": ("edit.pdf", st.session_state.edit_pdf_bytes, "application/pdf")},
                            data={"after_page": int(blank_after)}
                        )
                        if success:
                            update_live_pdf(response.content)
                        else:
                            display_error(response)

        with tabs[3]: # Annotate
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### Highlight Text")
                h_text = st.text_input("Text to Highlight")
                h_color = st.selectbox("Color", ["Yellow", "Green", "Blue", "Pink"])
                if st.button("🖍️ Apply Highlight"):
                    if not h_text: st.warning("Enter text")
                    else:
                        with st.spinner("Highlighting..."):
                            success, response = safe_api_call("/highlight-text",
                                files={"file": ("edit.pdf", st.session_state.edit_pdf_bytes, "application/pdf")},
                                data={"text_to_highlight": h_text, "color": h_color})
                            if success: update_live_pdf(response.content)
                            else: display_error(response)
            with c2:
                st.markdown("#### Comments & Notes")
                comm_pg = st.number_input("Page", min_value=1, value=1, key="com_pg")
                comm_t = st.text_area("Your Comment")
                if st.button("💬 Add Comment Note"):
                    if not comm_t: st.warning("Enter a comment")
                    else:
                        with st.spinner("Adding..."):
                            success, response = safe_api_call("/add-annotation",
                                files={"file": ("edit.pdf", st.session_state.edit_pdf_bytes, "application/pdf")},
                                data={"page_num": comm_pg, "comment": comm_t, "annotation_type": "text"})
                            if success: update_live_pdf(response.content)
                            else: display_error(response)

        with tabs[4]: # Security & Sign
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### Document Security")
                u_pw = st.text_input("Set Open Password", type="password")
                o_pw = st.text_input("Set Owner Password", type="password")
                al_p = st.checkbox("Allow Printing", value=True)
                al_e = st.checkbox("Allow Editing", value=True)
                if st.button("🔏 Lock PDF"):
                    if not u_pw: st.warning("User password recommended")
                    with st.spinner("Securing..."):
                        success, response = safe_api_call("/set-security",
                            files={"file": ("edit.pdf", st.session_state.edit_pdf_bytes, "application/pdf")},
                            data={"user_pw": u_pw, "owner_pw": o_pw, "allow_printing": al_p, "allow_editing": al_e})
                        if success: update_live_pdf(response.content, "✅ PDF Secured! Remember your passwords.")
                        else: display_error(response)
            with c2:
                st.markdown("#### Electronic Signature")

                sig_f  = st.file_uploader("Upload Signature (PNG)", type=["png"], key="sig_upload")

                # Page selector
                try:
                    _sig_doc   = fitz.open(stream=st.session_state.edit_pdf_bytes, filetype="pdf")
                    _sig_pages = len(_sig_doc)
                    _sig_doc.close()
                except Exception:
                    _sig_pages = 1

                sig_pg = st.number_input("Page", min_value=1, max_value=_sig_pages, value=1, key="sig_pg")

                # Render the selected page so user can see where to place signature
                try:
                    _prev_doc  = fitz.open(stream=st.session_state.edit_pdf_bytes, filetype="pdf")
                    _prev_page = _prev_doc[int(sig_pg) - 1]
                    _pw = _prev_page.rect.width
                    _ph = _prev_page.rect.height
                    _pix = _prev_page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2))
                    _prev_doc.close()
                    st.image(
                        Image.open(io.BytesIO(_pix.tobytes("png"))),
                        caption=f"Page {sig_pg} — use sliders below to position signature",
                        use_container_width=True,
                    )
                except Exception:
                    _pw, _ph = 595, 842   # A4 fallback

                st.caption("📍 Set signature position (in PDF points, origin = top-left)")

                col_x, col_y = st.columns(2)
                with col_x:
                    sig_x = st.slider(
                        "X position (left → right)",
                        min_value=0, max_value=int(_pw) - 50,
                        value=int(_pw * 0.55),   # default: right side
                        step=5, key="sig_x"
                    )
                with col_y:
                    sig_y = st.slider(
                        "Y position (top → bottom)",
                        min_value=0, max_value=int(_ph) - 20,
                        value=int(_ph * 0.80),   # default: near bottom
                        step=5, key="sig_y"
                    )

                col_w, col_h = st.columns(2)
                with col_w:
                    sig_w = st.slider("Width", min_value=40, max_value=300, value=150, step=10, key="sig_w")
                with col_h:
                    sig_h = st.slider("Height", min_value=20, max_value=150, value=50, step=5, key="sig_h")

                # Live preview: show signature overlaid on page at chosen position
                if sig_f is not None:
                    try:
                        sig_bytes = sig_f.read()
                        sig_f.seek(0)

                        _prev_doc2  = fitz.open(stream=st.session_state.edit_pdf_bytes, filetype="pdf")
                        _prev_page2 = _prev_doc2[int(sig_pg) - 1]

                        # Draw signature onto a copy of the page for preview
                        _prev_page2.insert_image(
                            fitz.Rect(sig_x, sig_y, sig_x + sig_w, sig_y + sig_h),
                            stream=sig_bytes,
                            keep_proportion=True,
                        )
                        _pix2 = _prev_page2.get_pixmap(matrix=fitz.Matrix(1.2, 1.2))
                        _prev_doc2.close()

                        st.markdown("**👁️ Preview — signature placement:**")
                        st.image(
                            Image.open(io.BytesIO(_pix2.tobytes("png"))),
                            use_container_width=True,
                        )
                    except Exception as _pe:
                        st.caption(f"Preview unavailable: {_pe}")

                if st.button("🖊️ Insert Signature", key="insert_sig_btn"):
                    if not sig_f:
                        st.warning("Upload a signature image first.")
                    else:
                        with st.spinner("Inserting signature…"):
                            sig_f.seek(0)
                            success, response = safe_api_call(
                                "/add-image",
                                files={
                                    "file":  ("edit.pdf", st.session_state.edit_pdf_bytes, "application/pdf"),
                                    "image": sig_f,
                                },
                                data={
                                    "page_num": int(sig_pg),
                                    "x":        sig_x,
                                    "y":        sig_y,
                                    "width":    sig_w,
                                    "height":   sig_h,
                                }
                            )
                        if success:
                            update_live_pdf(response.content, "✅ Signature Applied!")
                        else:
                            display_error(response)

        with tabs[5]: # Forms
            st.markdown("#### Form Creation (Beta)")
            st.info("Currently adds a standard text field and checkbox to page 1 for demonstration.")
            if st.button("🏗️ Create Sample Form Fields"):
                with st.spinner("Creating..."):
                    fields = [
                        {"page": 0, "name": "FullName", "type": "text", "rect": [100, 100, 300, 130]},
                        {"page": 0, "name": "Agreed", "type": "checkbox", "rect": [100, 150, 120, 170]}
                    ]
                    import json
                    success, response = safe_api_call("/create-form",
                        files={"file": ("edit.pdf", st.session_state.edit_pdf_bytes, "application/pdf")},
                        data={"fields_json": json.dumps(fields)})
                    if success: update_live_pdf(response.content)
                    else: display_error(response)

        st.divider()
        st.download_button("💾 Save Final PDF", st.session_state.edit_pdf_bytes,
            file_name=f"final_{uploaded_file.name}", mime="application/pdf", use_container_width=True)




# ================= SMART FORM FILLING =================
elif menu == "📄 Smart Form Filling":
    import json as _json

    st.header("📄 Smart Form Filling")
    st.write("Upload a PDF — every ___ blank is detected. Fill text fields or upload a signature image.")

    sff_file = st.file_uploader("📤 Upload PDF", type=["pdf"], key="sff_upload")

    if sff_file:
        st.success(f"✅ Uploaded: {sff_file.name}")

        # ── Detect blanks once per file ───────────────────────────────────
        _sff_key = f"sff_{sff_file.name}_{sff_file.size}"
        if _sff_key not in st.session_state:
            with st.spinner("🔍 Scanning for blank fields (___) …"):
                sff_file.seek(0)
                _ok, _resp = safe_api_call("/detect-form-fields", files={"file": sff_file})
                if _ok:
                    try:
                        _d = _resp.json()
                        st.session_state[_sff_key] = _d.get("blanks", [])
                        st.session_state[f"{_sff_key}_summary"] = _d.get("summary", "")
                    except Exception:
                        st.session_state[_sff_key] = []
                        st.session_state[f"{_sff_key}_summary"] = ""
                else:
                    st.session_state[_sff_key] = []
                    st.session_state[f"{_sff_key}_summary"] = ""
                    display_error("Could not detect fields.")

        _blanks  = st.session_state.get(_sff_key, [])
        _summary = st.session_state.get(f"{_sff_key}_summary", "")

        if not _blanks:
            st.info("No ___ blank fields detected in this PDF.")
        else:
            st.caption(f"🔎 {_summary}")
            st.markdown("---")
            st.markdown(f"### Fill in the {len(_blanks)} detected blank(s):")

            _fill_list   = []   # text fills
            _sig_uploads = []   # list of (clean_bytes, {"full_line","rect","page"})

            for _b in _blanks:
                _label      = _b.get("label", "") or f"Blank {_b['index']+1}"
                _blank_tok  = _b.get("blank", "")
                _full_line  = _b.get("full_line", "")
                _page       = _b.get("page", 0)
                _rect       = _b.get("rect")
                _is_sig     = _b.get("is_signature", False)
                _idx        = _b.get("index", 0)

                # Context line
                st.markdown(
                    f"<div style='background:#1a1a2e;padding:6px 12px;border-radius:6px;"
                    f"border-left:3px solid {'#ef9a9a' if _is_sig else '#5c6bc0'};"
                    f"margin-bottom:4px;font-size:0.85rem;color:#b0bec5;'>"
                    f"{'✍️ ' if _is_sig else ''}{_full_line}</div>",
                    unsafe_allow_html=True,
                )

                if _is_sig:
                    # ── SIGNATURE FIELD ───────────────────────────────────
                    st.markdown(f"**✍️ {_label}**")

                    # Show already-cleaned preview if available
                    _clean_key = f"sff_clean_img_{_idx}"
                    _clean_file_key = f"sff_clean_file_{_idx}"
                    if st.session_state.get(_clean_key):
                        st.image(st.session_state[_clean_key], width=200, caption="✅ Signature (background removed)")

                    _sig_up = st.file_uploader(
                        "Upload signature (PNG/JPG)",
                        type=["png", "jpg", "jpeg"],
                        key=f"sff_sig_{_idx}",
                        help="Background will be removed automatically.",
                    )
                    if _sig_up:
                        _raw = _sig_up.read()
                        _sig_up.seek(0)

                        # Auto-remove background on upload
                        if not st.session_state.get(_clean_key):
                            with st.spinner("Removing background…"):
                                _ok_bg, _r_bg = safe_api_call(
                                    "/clean-and-extract-signature",
                                    files={"image": (_sig_up.name, _raw, "image/png")},
                                )
                            if _ok_bg:
                                try:
                                    _cb64 = _r_bg.json().get("clean_image_b64", "")
                                except Exception:
                                    _cb64 = ""
                                if _cb64:
                                    import base64 as _b64m
                                    _clean_bytes = _b64m.b64decode(_cb64)
                                    st.session_state[_clean_key]      = _clean_bytes
                                    st.session_state[_clean_file_key] = _clean_bytes
                                    st.image(_clean_bytes, width=200, caption="✅ Background removed")
                                    st.rerun()
                                else:
                                    # BG removal returned nothing — show original
                                    st.session_state[_clean_key]      = _raw
                                    st.session_state[_clean_file_key] = _raw
                                    st.image(_raw, width=160, caption="Preview (BG removal unavailable)")
                            else:
                                # API call failed — use original
                                st.session_state[_clean_key]      = _raw
                                st.session_state[_clean_file_key] = _raw
                                st.image(_raw, width=160, caption="Preview")

                        # Add to uploads list using the cleaned bytes
                        _clean_bytes_for_upload = st.session_state.get(_clean_file_key, _raw)
                        _sig_uploads.append((_clean_bytes_for_upload, {
                            "full_line": _full_line,
                            "rect":      _rect,
                            "page":      _page,
                        }))

                else:
                    # ── TEXT FIELD ────────────────────────────────────────
                    _val = st.text_input(
                        f"✏️ {_label}",
                        key=f"sff_inp_{_idx}",
                        placeholder=f"Enter value for: {_label}",
                    )
                    if _val.strip():
                        _fill_list.append({
                            "full_line": _full_line,
                            "blank":     _blank_tok,
                            "value":     _val.strip(),
                            "page":      _page,
                            "rect":      _rect,
                        })

                st.markdown("")

            st.markdown("---")
            if st.button("✍️ Fill & Download PDF", use_container_width=True, type="primary"):
                if not api_status:
                    display_error("API Server is offline.")
                elif not _fill_list and not _sig_uploads:
                    st.warning("Please fill in at least one blank before downloading.")
                else:
                    with st.spinner("Filling blanks and generating PDF…"):
                        sff_file.seek(0)

                        # Build multipart files list
                        # PDF as "file", each cleaned signature as "sig_files"
                        _files = [("file", (sff_file.name, sff_file, "application/pdf"))]
                        _meta  = {}
                        for _si, (_clean_bytes, _info) in enumerate(_sig_uploads):
                            _files.append(("sig_files", (f"sig_{_si}.png", _clean_bytes, "image/png")))
                            _meta[f"sig_{_si}"] = _info

                        import requests as _req
                        _r = _req.post(
                            f"{API_URL}/fill-form",
                            files=_files,
                            data={
                                "fills":    _json.dumps(_fill_list),
                                "sig_meta": _json.dumps(_meta),
                            },
                            timeout=120,
                        )

                    if _r.status_code == 200:
                        display_success("✅ PDF filled successfully!")
                        st.download_button(
                            "⬇️ Download Filled PDF",
                            data=_r.content,
                            file_name=f"filled_{sff_file.name}",
                            mime="application/pdf",
                        )
                    else:
                        display_error(_r.text)

# ================= IMPROVE WRITING =================
elif menu == "✍ Improve Writing":
    st.header("✍ AI Improve Writing")
    st.write("Enhance text quality and readability")
    
    uploaded_file = st.file_uploader(
        "📤 Upload PDF to Improve",
        type=["pdf"],
        key="improve_upload"
    )

    if uploaded_file:
        st.success(f"✅ File uploaded: {uploaded_file.name}")

        current_improve_source = f"{uploaded_file.name}_{uploaded_file.size}"
        if st.session_state.get("improve_source_key") != current_improve_source:
            for _key in [
                "improve_text",
                "improve_pdf_bytes",
                "improve_filename",
                "improve_original_len",
                "improve_level_used",
            ]:
                st.session_state.pop(_key, None)
            st.session_state["improve_source_key"] = current_improve_source
        
        improvement_level = st.selectbox(
            "Improvement Level",
            ["Basic", "Intermediate", "Advanced"],
            key="improve_level"
        )
        
        if st.button("✨ Improve Writing"):
            if not api_status:
                display_error("API Server is offline")
            else:
                with st.spinner("🔄 Improving text..."):
                    success, response = safe_api_call(
                        "/improve-writing",
                        files={"file": uploaded_file},
                        data={"level": improvement_level}
                    )
                
                if success:
                    try:
                        result = response.json()
                    except Exception:
                        st.error("❌ Invalid JSON response from API")
                        st.text(response.text)
                        st.stop()
                    display_success("✅ Writing improved!")

                    improved_text = result.get("improved_text", "")
                    pdf_b64 = result.get("pdf_base64", "")
                    pdf_bytes = None

                    if pdf_b64:
                        try:
                            pdf_bytes = base64.b64decode(pdf_b64)
                        except Exception as _b64_err:
                            logging.warning(f"Improve Writing PDF decode failed: {_b64_err}")
                            pdf_bytes = None

                    # Fallback: create a simple text PDF if backend PDF is unavailable.
                    if not pdf_bytes and improved_text:
                        try:
                            from fpdf import FPDF
                            _pdf = FPDF(unit="pt", format="letter")
                            _pdf.set_auto_page_break(auto=True, margin=40)
                            _pdf.add_page()
                            _pdf.set_font("Helvetica", size=11)
                            for _line in improved_text.splitlines():
                                safe = _line.encode("latin-1", "replace").decode("latin-1")
                                if safe.strip():
                                    _pdf.multi_cell(0, 16, text=safe)
                                else:
                                    _pdf.ln(8)
                            _raw_pdf = _pdf.output()
                            pdf_bytes = (
                                _raw_pdf.encode("latin-1")
                                if isinstance(_raw_pdf, str)
                                else bytes(_raw_pdf)
                            )
                        except Exception as _pe:
                            logging.warning(f"Improve Writing fallback PDF build failed: {_pe}")
                            pdf_bytes = None

                    st.session_state["improve_text"] = improved_text
                    st.session_state["improve_pdf_bytes"] = pdf_bytes
                    st.session_state["improve_filename"] = uploaded_file.name
                    st.session_state["improve_original_len"] = result.get("original_text_length", 0)
                    st.session_state["improve_level_used"] = improvement_level
                else:
                    display_error(response)

        if st.session_state.get("improve_text"):
            improved_text = st.session_state["improve_text"]
            pdf_bytes = st.session_state.get("improve_pdf_bytes")
            source_name = st.session_state.get("improve_filename", uploaded_file.name)
            base_name = os.path.splitext(source_name)[0]

            tabs = st.tabs(["✍ Improved Text", "👁️ Preview", "📥 Download"])

            with tabs[0]:
                st.text_area("Improved Text", improved_text, height=350, disabled=True)

            with tabs[1]:
                if pdf_bytes:
                    display_pdf_preview(pdf_bytes, height=500)
                else:
                    st.warning("PDF preview unavailable. You can still download the improved text.")

            with tabs[2]:
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    if pdf_bytes:
                        st.download_button(
                            "⬇️ Download Improved PDF",
                            pdf_bytes,
                            file_name=f"improved_{base_name}.pdf",
                            mime="application/pdf"
                        )
                    else:
                        st.warning("PDF download unavailable.")
                with col_d2:
                    st.download_button(
                        "⬇️ Download Improved Text",
                        improved_text,
                        file_name=f"improved_{base_name}.txt",
                        mime="text/plain"
                    )



# ================= CONVERT TO PDF =================
elif menu == "🔄 Convert Other Files to PDF":
    st.header("🔄 Convert Files to PDF")
    st.write("Convert various file formats to PDF — layout, fonts and sizes preserved")

    uploaded_file = st.file_uploader(
        "📤 Upload File",
        type=["docx", "doc", "txt", "html", "md", "jpg", "jpeg", "png", "ppt", "pptx", "xls", "xlsx"],
        key="convert_to_pdf_upload"
    )

    if uploaded_file:
        st.success(f"✅ File uploaded: {uploaded_file.name}")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("File Type", os.path.splitext(uploaded_file.name)[1].upper() or "Unknown")
        with col2:
            st.metric("File Size", f"{uploaded_file.size / 1024:.2f} KB")

        if st.button("🔄 Convert to PDF"):
            if not api_status:
                display_error("API Server is offline")
            else:
                with st.spinner("🔄 Converting to PDF..."):
                    success, response = safe_api_call(
                        "/convert-to-pdf",
                        files={"file": uploaded_file}
                    )

                if success:
                    is_pdf = (response.content[:4] == b"%PDF" or
                              "pdf" in response.headers.get("content-type", "").lower())
                    if is_pdf:
                        display_success("✅ Converted successfully!")
                        base_name = os.path.splitext(uploaded_file.name)[0]
                        st.download_button(
                            "⬇️ Download PDF",
                            response.content,
                            file_name=f"{base_name}.pdf",
                            mime="application/pdf"
                        )
                    else:
                        try:
                            err = response.json().get("detail", response.text)
                        except Exception:
                            err = response.text
                        display_error(f"Conversion failed: {err}")
                else:
                    display_error(f"Conversion failed: {response}")

# ================= CONVERT FROM PDF =================
elif menu == "🔄 Convert PDF to Other Files":
    st.header("🔄 Convert PDF to Other Formats")
    st.write("Export PDF to Word, Text, HTML, Markdown, Images, PowerPoint or Excel")

    uploaded_file = st.file_uploader(
        "📤 Upload PDF",
        type=["pdf"],
        key="convert_from_pdf_upload"
    )

    if uploaded_file:
        st.success(f"✅ PDF uploaded: {uploaded_file.name}")
        st.metric("File Size", f"{uploaded_file.size / 1024:.2f} KB")

        FORMAT_MAP = {
            "Word (.docx)":       ("docx",  ".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            "Text (.txt)":        ("txt",   ".txt",  "text/plain"),
            "HTML (.html)":       ("html",  ".html", "text/html"),
            "Markdown (.md)":     ("md",    ".md",   "text/markdown"),
            "JPG Image (.jpg)":   ("jpg",   ".jpg",  "image/jpeg"),
            "JPEG Image (.jpeg)": ("jpeg",  ".jpeg", "image/jpeg"),
            "PNG Image (.png)":   ("png",   ".png",  "image/png"),
            "PowerPoint (.pptx)": ("pptx",  ".pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
            "PowerPoint (.ppt)":  ("ppt",   ".ppt",  "application/vnd.ms-powerpoint"),
            "Excel (.xlsx)":      ("xlsx",  ".xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "Excel (.xls)":       ("xls",   ".xls",  "application/vnd.ms-excel"),
        }

        output_format = st.selectbox(
            "Select Output Format",
            list(FORMAT_MAP.keys())
        )

        if output_format in ["JPG Image (.jpg)", "JPEG Image (.jpeg)", "PNG Image (.png)"]:
            st.info("📄 Single-page PDF → image file. Multi-page PDF → ZIP of images.")

        if output_format == "Word (.docx)":
            st.info("📌 Word output renders each page as an image inside the DOCX — guarantees identical layout, fonts, and positioning as the original PDF.")

        if st.button("🔄 Convert PDF"):
            if not api_status:
                display_error("API Server is offline")
            else:
                fmt, ext, mime = FORMAT_MAP[output_format]
                with st.spinner(f"🔄 Converting to {output_format}..."):
                    success, response = safe_api_call(
                        "/convert-from-pdf",
                        files={"file": uploaded_file},
                        data={"format": fmt}
                    )

                if success:
                    display_success(f"✅ PDF converted to {output_format}!")
                    base_name = os.path.splitext(uploaded_file.name)[0]
                    # Multi-page images come back as ZIP
                    actual_ext = ext
                    actual_mime = mime
                    if fmt in ("jpg", "jpeg", "png") and response.content[:2] == b"PK":
                        actual_ext = ".zip"
                        actual_mime = "application/zip"
                    st.download_button(
                        f"⬇️ Download {output_format}",
                        response.content,
                        file_name=f"{base_name}{actual_ext}",
                        mime=actual_mime
                    )
                else:
                    display_error(f"Conversion failed: {response}")

# ================= SUMMARIZER =================
elif menu == "🤖 Summarize PDF":
    st.header("🤖 AI PDF Summarizer")
    st.write("Generate intelligent summaries of your PDFs")
    
    uploaded_file = st.file_uploader(
        "📤 Upload PDF",
        type=["pdf"],
        key="summarizer_upload"
    )

    if uploaded_file:
        st.success(f"✅ PDF uploaded: {uploaded_file.name}")
        
        col1, col2 = st.columns(2)

        with col1:
            summary_length = st.selectbox(
                "Summary Length",
                ["Short (100 words)", "Medium (250 words)", "Long (500 words)"],
                index=1,
                key="summary_length"
            )

        with col2:
            st.info("💡 Tip: Use 'Long' for detailed documents")
        
        if st.button("📝 Generate Summary"):
            if not api_status:
                display_error("API Server is offline")
            else:
                with st.spinner("⏳ Generating summary..."):
                    success, response = safe_api_call(
                        "/summarize-pdf",
                        files={"file": uploaded_file},
                        data={"summary_length": summary_length}
                    )
                
                if success:
                    data = response.json()
                    display_success("✅ Summary generated!")

                    summary_text    = data.get("summary", "No summary available")
                    key_points_text = data.get("key_points", "")

                    # ── Build summary PDF ─────────────────────────────────
                    _pdf_bytes = None
                    try:
                        import fitz
                        _doc = fitz.open()

                        def _safe(s):
                            """Replace characters helv can't render."""
                            return (s.replace("\u2014", "-")
                                     .replace("\u2013", "-")
                                     .replace("\u2022", "*")
                                     .replace("\u2019", "'")
                                     .replace("\u2018", "'")
                                     .replace("\u201c", '"')
                                     .replace("\u201d", '"')
                                     .replace("\u2026", "..."))

                        def _write_page(doc, title, body):
                            """Write title + body onto one or more A4 pages with proper spacing."""
                            W, H    = 595, 842
                            LEFT    = 50
                            RIGHT   = 545
                            TOP     = 60
                            BOTTOM  = 810
                            LINE_H  = 16   # normal line height
                            BULLET_GAP = 8  # extra gap after each bullet

                            title = _safe(title)
                            body  = _safe(body)

                            page = doc.new_page(width=W, height=H)
                            y = TOP

                            # ── Title ──────────────────────────────────────
                            page.insert_text(
                                fitz.Point(LEFT, y),
                                title,
                                fontsize=15,
                                fontname="helv",
                                color=(0, 0, 0),
                            )
                            y += 24

                            # Divider line
                            page.draw_line(
                                fitz.Point(LEFT, y), fitz.Point(RIGHT, y),
                                color=(0.5, 0.5, 0.5), width=0.7
                            )
                            y += 18

                            # ── Body: paragraph by paragraph ───────────────
                            paragraphs = body.split("\n")
                            for para in paragraphs:
                                para = para.strip()

                                # Blank line = small vertical gap
                                if not para:
                                    y += 6
                                    continue

                                # New page if not enough room
                                if y + LINE_H > BOTTOM:
                                    page = doc.new_page(width=W, height=H)
                                    y = TOP

                                is_bullet = para.startswith(("•", "*", "-"))

                                # Indent bullet text slightly
                                x_start = LEFT + 12 if is_bullet else LEFT

                                # Render paragraph into a textbox so long lines wrap
                                rect = fitz.Rect(x_start, y, RIGHT, BOTTOM)
                                overflow = page.insert_textbox(
                                    rect,
                                    para,
                                    fontsize=11,
                                    fontname="helv",
                                    color=(0, 0, 0),
                                    align=0,
                                )

                                if overflow < 0:
                                    # Text didn't fit — start new page and retry
                                    page = doc.new_page(width=W, height=H)
                                    y = TOP
                                    page.insert_textbox(
                                        fitz.Rect(x_start, y, RIGHT, BOTTOM),
                                        para,
                                        fontsize=11,
                                        fontname="helv",
                                        color=(0, 0, 0),
                                        align=0,
                                    )

                                # Estimate vertical space consumed
                                chars_per_line = (RIGHT - x_start) / 6.5
                                lines_used = max(1, len(para) / chars_per_line)
                                y += int(lines_used * LINE_H) + 4

                                # Extra gap after bullet points for readability
                                if is_bullet:
                                    y += BULLET_GAP

                        # Write Summary page(s)
                        _write_page(
                            _doc,
                            f"Summary: {uploaded_file.name}",
                            str(summary_text)
                        )

                        # Write Key Points page(s)
                        if key_points_text and str(key_points_text).strip():
                            _write_page(_doc, "Key Points", str(key_points_text))

                        _pdf_bytes = bytes(_doc.tobytes())
                        _doc.close()

                    except Exception as _se:
                        logging.warning(f"Summary PDF build failed: {_se}")
                        _pdf_bytes = None

                    st.session_state["summary_pdf_bytes"] = _pdf_bytes
                    st.session_state["summary_text"] = summary_text
                    st.session_state["summary_key_points"] = key_points_text
                    st.session_state["summary_filename"] = uploaded_file.name
                    st.session_state["summary_orig_len"] = data.get("original_length", 0)
                    st.session_state["summary_summ_len"] = data.get("summary_length", 0)

                else:
                    display_error(response)

            # ── Always show results if available ──────────────────────
            if st.session_state.get("summary_text"):
                summary_text    = st.session_state["summary_text"]
                key_points_text = st.session_state["summary_key_points"]
                _pdf_bytes      = st.session_state.get("summary_pdf_bytes")
                fname           = st.session_state.get("summary_filename", "document.pdf")
                orig_len        = st.session_state.get("summary_orig_len", 0)
                summ_len        = st.session_state.get("summary_summ_len", 0)

                tabs = st.tabs(["📌 Summary", "🔑 Key Points", "📊 Statistics", "📥 Download"])

                with tabs[0]:
                    st.write(summary_text)

                with tabs[1]:
                    if isinstance(key_points_text, list):
                        for i, pt in enumerate(key_points_text, 1):
                            st.markdown(f"**{i}.** {pt}")
                    else:
                        # Parse bullet lines and display each as a proper markdown bullet
                        kp_lines = [l.strip() for l in str(key_points_text).splitlines() if l.strip()]
                        for kp in kp_lines:
                            # Normalise bullet symbol
                            if kp.startswith(("•", "*", "-")):
                                kp = kp[1:].strip()
                            st.markdown(f"• {kp}")

                with tabs[2]:
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Original", f"{orig_len:,} chars")
                    with c2:
                        st.metric("Summary", f"{summ_len:,} chars")
                    with c3:
                        ratio = round((1 - summ_len / max(orig_len, 1)) * 100, 1)
                        st.metric("Compression", f"{ratio}%")

                with tabs[3]:
                    base = fname.replace(".pdf", "")
                    col_d1, col_d2 = st.columns(2)
                    with col_d1:
                        if _pdf_bytes:
                            st.download_button(
                                "⬇️ Download Summary PDF",
                                data=_pdf_bytes,
                                file_name=f"summary_{base}.pdf",
                                mime="application/pdf",
                                key="download_summary_pdf"
                            )
                        else:
                            st.warning("PDF generation failed — use text download.")
                    with col_d2:
                        st.download_button(
                            "⬇️ Download Summary Text",
                            data=summary_text,
                            file_name=f"summary_{base}.txt",
                            mime="text/plain",
                            key="download_summary_txt"
                        )


# ================= TRANSLATE PDF =================
elif menu == "🌍 Translate PDF":
    st.header("🌍 Translate PDF")
    
    uploaded_file = st.file_uploader("Drag and drop file here", type=["pdf"], key="translate_upload")
    
    if uploaded_file:
        st.success(f"✅ PDF uploaded: {uploaded_file.name}")
        
        col1, col2 = st.columns(2)
        with col1:
            source_language = st.selectbox("Source Language", ["English", "Auto Detect", "Hindi", "French", "Spanish", "German"])
        with col2:
            target_language = st.selectbox("Target Language", ["Hindi", "English", "French", "Spanish", "German"])
            
        if st.button("🌐 Translate PDF", use_container_width=True):
            if not api_status:
                st.error("❌ API Server is offline")
            else:
                with st.spinner("Translating document..."):
                    success, response = safe_api_call(
                        "/translate-pdf",
                        files={"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")},
                        data={
                            "source_language": source_language,
                            "target_language": target_language,
                            "text_only": "false"
                        },
                        timeout=300
                    )
                    
                if success and hasattr(response, "json"):
                    data = response.json()
                    if data.get("status") == "success":
                        st.success(f"✅ Successfully translated to {target_language}!")
                        
                        tabs = st.tabs(["📄 Translation", "📊 Details", "📥 Download"])
                        
                        with tabs[0]:
                            st.text_area("Translated Text", data.get("translated_text", ""), height=400)
                            
                        with tabs[1]:
                            st.write(f"**Original Language:** {data.get('source_language')}")
                            st.write(f"**Target Language:** {data.get('target_language')}")
                            st.write(f"**Original Text Length:** {data.get('original_text_length')} characters")
                            
                        with tabs[2]:
                            base_name = os.path.splitext(uploaded_file.name)[0]
                            # Download text
                            st.download_button(
                                "⬇️ Download Translated Text",
                                data=data.get("translated_text", ""),
                                file_name=f"{base_name}_{target_language}.txt",
                                mime="text/plain",
                                use_container_width=True
                            )
                            # Download PDF
                            pdf_base64 = data.get("pdf_base64")
                            if pdf_base64:
                                pdf_bytes = base64.b64decode(pdf_base64)
                                st.download_button(
                                    "⬇️ Download Translated PDF",
                                    data=pdf_bytes,
                                    file_name=f"{base_name}_{target_language}.pdf",
                                    mime="application/pdf",
                                    use_container_width=True
                                )
                    else:
                        st.error("Translation failed")
                else:
                    display_error(response)


# ================= FOOTER =================
st.divider()
st.markdown("""
    <div style='text-align: center; padding: 20px;'>
        <p>🤖 <strong>AI PDF Editor</strong> | Powered by Advanced AI & ML</p>
        <p>© 2026 All Rights Reserved | <small>v1.0</small></p>
    </div>
    """, unsafe_allow_html=True)
