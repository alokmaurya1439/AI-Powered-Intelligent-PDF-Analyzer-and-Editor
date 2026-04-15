import streamlit as st
import streamlit.components.v1 as components
import sys
import requests
import os
import base64
from pathlib import Path



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


def safe_api_call(endpoint: str, files=None, data=None, method="POST"):
    try:
        formatted_files = None
        if files:
            formatted_files = {}
            for key, value in files.items():
                if isinstance(value, tuple):
                    formatted_files[key] = value
                elif hasattr(value, "read") and hasattr(value, "name"):
                    value.seek(0)
                    formatted_files[key] = (value.name, value, "application/pdf")
                elif isinstance(value, (bytes, bytearray)):
                    formatted_files[key] = (f"{key}.pdf", value, "application/pdf")
                else:
                    formatted_files[key] = value

        if method == "POST":
            response = requests.post(
                f"{API_URL}{endpoint}",
                files=formatted_files,
                data=data,
                timeout=300
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
    5. **📄 Smart Form Filling** - Auto-fill PDF forms
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
            confidence_threshold = st.slider(
                "Confidence Threshold",
                0.0, 1.0, 0.7
            )
        
        if st.button("🔍 Detect Errors", key="detect_btn"):
            if not api_status:
                display_error("API Server is offline")
            else:
                with st.spinner("🔄 Analyzing PDF..."):
                    success, response = safe_api_call(
                        "/error-detector",
                        files={"file": uploaded_file}
                    )
                
                if success:
                    st.session_state.error_detect_data = response.json()
                    st.session_state.error_detect_file_name = uploaded_file.name
                    st.session_state.error_detect_file_bytes = uploaded_file.getvalue()
                    display_success("✅ Analysis complete!")
                else:
                    display_error(response)
    
    # Display Results
    if st.session_state.error_detect_data:
        st.divider()
        st.subheader("📊 Results")
        
        data = st.session_state.error_detect_data
        
        tabs = st.tabs(["�️ Preview", "📝 Text", "📊 Metadata", "⭐ Quality", "🧠 Errors", "📥 Download"])
        
        with tabs[0]:
            if st.session_state.error_detect_file_bytes:
                display_pdf_preview(st.session_state.error_detect_file_bytes, height=720)
            else:
                st.warning("PDF preview not available.")
                st.write("Use the Download tab to save the PDF and view it in your browser.")

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
            if quality_data:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Readability", quality_data.get("readability", "N/A"))
                with col2:
                    st.metric("Clarity", quality_data.get("clarity", "N/A"))
                with col3:
                    st.metric("Formatting", quality_data.get("formatting", "N/A"))
            st.text_area(
                "Quality Details",
                str(quality_data),
                height=300,
                disabled=True
            )
        
        with tabs[4]:
            errors = data.get("errors", "No errors detected")
            st.text_area(
                "Detected Errors",
                errors,
                height=400,
                disabled=True
            )
        
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
                    
                    if success and "application/pdf" in response.headers.get("content-type", ""):
                        original_name = os.path.splitext(
                            st.session_state.error_detect_file_name
                        )[0]
                        display_success("✅ Corrected PDF generated!")
                        st.download_button(
                            label="⬇️ Download Corrected PDF",
                            data=response.content,
                            file_name=f"{original_name}_corrected.pdf",
                            mime="application/pdf"
                        )
                    else:
                        display_error("Failed to generate corrected PDF")

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
        
        edit_option = st.selectbox(
            "Select Edit Option",
            [
                "Replace Text",
                "Add Image",
                "Rotate Pages",
                "Delete Pages",
                "Add Watermark",
                "Merge PDFs",
                "Split PDF"
            ]
        )
        
        if edit_option == "Replace Text":
            col1, col2 = st.columns(2)
            with col1:
                old_text = st.text_input("Text to find")
            with col2:
                new_text = st.text_input("Replace with")
            
            if st.button("Replace Text"):
                if not old_text:
                    st.warning("Please enter text to find")
                else:
                    if not api_status:
                        display_error("API Server is offline")
                    else:
                        with st.spinner("Processing..."):
                            success, response = safe_api_call(
                                "/replace-text",
                                files={"file": uploaded_file},
                                data={"old_text": old_text, "new_text": new_text}
                            )
                        
                        if success:
                            display_success("✅ Text replaced!")
                            st.download_button(
                                "Download Edited PDF",
                                response.content,
                                file_name=f"edited_{uploaded_file.name}",
                                mime="application/pdf"
                            )
                        else:
                            display_error(response)
        
        elif edit_option == "Add Watermark":
            watermark_text = st.text_input("Watermark text")
            
            if st.button("Add Watermark"):
                if not watermark_text:
                    st.warning("Please enter watermark text")
                else:
                    if not api_status:
                        display_error("API Server is offline")
                    else:
                        with st.spinner("Adding watermark..."):
                            success, response = safe_api_call(
                                "/add-watermark",
                                files={"file": uploaded_file},
                                data={"watermark_text": watermark_text}
                            )
                        
                        if success:
                            display_success("✅ Watermark added!")
                            st.download_button(
                                "Download PDF with Watermark",
                                response.content,
                                file_name=f"watermarked_{uploaded_file.name}",
                                mime="application/pdf"
                            )
                        else:
                            display_error(response)
        
        elif edit_option == "Rotate Pages":
            angle = st.selectbox("Rotation Angle", [90, 180, 270])
            if st.button("Rotate Pages"):
                if not api_status:
                    display_error("API Server is offline")
                else:
                    with st.spinner("Rotating pages..."):
                        success, response = safe_api_call(
                            "/rotate-pages",
                            files={"file": uploaded_file},
                            data={"angle": angle}
                        )
                    if success:
                        display_success("✅ Pages rotated!")
                        st.download_button(
                            "Download Rotated PDF",
                            response.content,
                            file_name=f"rotated_{uploaded_file.name}",
                            mime="application/pdf"
                        )
                    else:
                        display_error(response)
        
        elif edit_option == "Delete Pages":
            pages_to_delete = st.text_input("Pages to delete (e.g. 1, 3, 5-7)")
            if st.button("Delete Pages"):
                if not pages_to_delete:
                    st.warning("Please enter pages to delete")
                else:
                    if not api_status:
                        display_error("API Server is offline")
                    else:
                        with st.spinner("Deleting pages..."):
                            success, response = safe_api_call(
                                "/delete-pages",
                                files={"file": uploaded_file},
                                data={"pages": pages_to_delete}
                            )
                        if success:
                            display_success("✅ Pages deleted!")
                            st.download_button(
                                "Download Trimmed PDF",
                                response.content,
                                file_name=f"trimmed_{uploaded_file.name}",
                                mime="application/pdf"
                            )
                        else:
                            display_error(response)
        
        elif edit_option == "Merge PDFs":
            additional_files = st.file_uploader("Upload additional PDFs to merge with base PDF", type=["pdf"], accept_multiple_files=True)
            if st.button("Merge PDFs"):
                if not additional_files:
                    st.warning("Please upload at least one additional PDF")
                else:
                    if not api_status:
                        display_error("API Server is offline")
                    else:
                        with st.spinner("Merging PDFs..."):
                            # Prepare multiple files using requests format
                            files_param = []
                            uploaded_file.seek(0)
                            files_param.append(("files", (uploaded_file.name, uploaded_file, "application/pdf")))
                            for af in additional_files:
                                af.seek(0)
                                files_param.append(("files", (af.name, af, "application/pdf")))
                            
                            try:
                                resp = requests.post(
                                    f"{API_URL}/merge-pdfs",
                                    files=files_param,
                                    timeout=300
                                )
                                if resp.status_code == 200:
                                    display_success("✅ PDFs merged!")
                                    st.download_button(
                                        "Download Merged PDF",
                                        resp.content,
                                        file_name=f"merged_{uploaded_file.name}",
                                        mime="application/pdf"
                                    )
                                else:
                                    display_error(resp.text)
                            except Exception as e:
                                display_error(str(e))
        
        elif edit_option == "Split PDF":
            col1, col2 = st.columns(2)
            with col1:
                start_page = st.number_input("Start Page", min_value=1, value=1)
            with col2:
                end_page = st.number_input("End Page (0 for till end)", min_value=0, value=0)
            
            if st.button("Split PDF"):
                if not api_status:
                    display_error("API Server is offline")
                else:
                    with st.spinner("Splitting PDF..."):
                        success, response = safe_api_call(
                            "/split-pdf",
                            files={"file": uploaded_file},
                            data={"start_page": start_page, "end_page": end_page}
                        )
                    if success:
                        display_success("✅ PDF split into zip!")
                        st.download_button(
                            "Download Split PDFs (ZIP)",
                            response.content,
                            file_name=f"split_{uploaded_file.name}.zip",
                            mime="application/zip"
                        )
                    else:
                        display_error(response)
        
        elif edit_option == "Add Image":
            image_file = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg"])
            col1, col2 = st.columns(2)
            with col1:
                page_num = st.number_input("Page Number", min_value=1, value=1)
                x_pos = st.number_input("X Position", value=0.0)
                y_pos = st.number_input("Y Position", value=0.0)
            with col2:
                img_width = st.number_input("Image Width", min_value=10.0, value=100.0)
                img_height = st.number_input("Image Height", min_value=10.0, value=100.0)
                
            if st.button("Add Image"):
                if not image_file:
                    st.warning("Please upload an image")
                else:
                    if not api_status:
                        display_error("API Server is offline")
                    else:
                        with st.spinner("Adding image..."):
                            success, response = safe_api_call(
                                "/add-image",
                                files={"file": uploaded_file, "image": image_file},
                                data={
                                    "page_num": page_num,
                                    "x": x_pos,
                                    "y": y_pos,
                                    "width": img_width,
                                    "height": img_height
                                }
                            )
                        if success:
                            display_success("✅ Image added!")
                            st.download_button(
                                "Download PDF with Image",
                                response.content,
                                file_name=f"with_image_{uploaded_file.name}",
                                mime="application/pdf"
                            )
                        else:
                            display_error(response)
# ================= SMART FORM FILLING =================
elif menu == "📄 Smart Form Filling":
    st.header("📄 Smart Form Filling")
    st.write("Automatically detect and fill PDF form fields")
    
    uploaded_file = st.file_uploader(
        "📤 Upload Form PDF",
        type=["pdf"],
        key="form_fill_upload"
    )
    
    if uploaded_file:
        st.success(f"✅ Form uploaded: {uploaded_file.name}")
        
        ss_key = f"fields_{uploaded_file.name}_{uploaded_file.size}"
        if ss_key not in st.session_state:
            with st.spinner("Detecting form fields..."):
                uploaded_file.seek(0)
                success, response = safe_api_call(
                    "/detect-form-fields",
                    files={"file": uploaded_file}
                )
                if success:
                    try:
                        data = response.json()
                        st.session_state[ss_key] = data.get("fields", [])
                        st.session_state[f"ph_{ss_key}"] = data.get("placeholders", [])
                    except Exception:
                        st.session_state[ss_key] = []
                        st.session_state[f"ph_{ss_key}"] = []
                else:
                    st.session_state[ss_key] = []
                    st.session_state[f"ph_{ss_key}"] = []
                    display_error("Failed to detect fields")
        
        fields = st.session_state.get(ss_key, [])
        placeholders = st.session_state.get(f"ph_{ss_key}", [])
        
        if not fields and not placeholders:
            st.info("No fillable blank spaces or form fields detected in this PDF.")
        else:
            st.write("### Please fill in the detected blanks:")
            import json
            form_data_dict = {}
            text_replace_dict = {}
            
            if fields:
                st.markdown("#### Form Fields")
                for field in fields:
                    field_name = field.get("name", "Unknown Field")
                    if field.get("type", "").lower() in ["checkbox", "radio"]:
                        val = st.checkbox(f"{field_name}", value=bool(field.get("value")), key=f"f_{field_name}")
                        form_data_dict[field_name] = "Yes" if val else "Off"
                    else:
                        val = st.text_input(f"{field_name}", value=str(field.get("value") or ""), key=f"f_{field_name}")
                        form_data_dict[field_name] = val
            
            if placeholders:
                st.markdown("#### Detect Visual Blanks")
                for i, ph in enumerate(placeholders):
                    val = st.text_input(f"Replacement for: {ph.strip()}", key=f"p_{i}_{hash(ph)}")
                    if val:
                        text_replace_dict[ph] = val
                    
            if st.button("✍️ Fill Form"):
                if not api_status:
                    display_error("API Server is offline")
                else:
                    with st.spinner("Filling form..."):
                        uploaded_file.seek(0)
                        success, response = safe_api_call(
                            "/fill-form",
                            files={"file": uploaded_file},
                            data={
                                "form_data": json.dumps(form_data_dict),
                                "text_replacements": json.dumps(text_replace_dict)
                            }
                        )
                    
                    if success:
                        display_success("✅ Form filled successfully!")
                        st.download_button(
                            "⬇️ Download Filled Form",
                            response.content,
                            file_name=f"filled_{uploaded_file.name}",
                            mime="application/pdf"
                        )
                    else:
                        display_error(response)


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
                    
                    st.text_area(
                        "Improved Text",
                        result.get("improved_text", ""),
                        height=300,
                        disabled=True
                    )

                    pdf_base64 = result.get("pdf_base64")
                    if pdf_base64:
                        pdf_bytes = base64.b64decode(pdf_base64)
                        display_pdf_preview(pdf_bytes, height=600)
                        st.divider()
                        st.download_button(
                            "⬇️ Download Improved Text",
                            result.get("improved_text", ""),
                            file_name=f"improved_{uploaded_file.name.replace('.pdf', '.txt')}",
                            mime="text/plain"
                        )
                    else:
                        st.warning("PDF output unavailable.")
                else:
                    display_error(response)

# ================= FIX FORMATTING =================
elif menu == "🧹 Fix Formatting":
    st.header("🧹 AI Fix Formatting")
    st.write("Normalize and fix document formatting")
    
    uploaded_file = st.file_uploader(
        "📤 Upload PDF to Fix",
        type=["pdf"],
        key="format_upload"
    )
    
    if uploaded_file:
        st.success(f"✅ File uploaded: {uploaded_file.name}")
        
        formatting_options = st.multiselect(
            "Select Formatting Options",
            ["Fix spacing", "Fix indentation", "Fix alignment", "Fix fonts"],
            default=["Fix spacing"]
        )
        
        if st.button("🔧 Fix Formatting"):
            if not api_status:
                display_error("API Server is offline")
            else:
                with st.spinner("⏳ Fixing formatting..."):
                    success, response = safe_api_call(
                        "/fix-formatting",
                        files={"file": uploaded_file}
                    )
                
                if success:
                    try:
                        result = response.json()
                    except Exception:
                        st.error("❌ Invalid JSON response from API")
                        st.text(response.text)
                        st.stop()
                    display_success("✅ Formatting fixed!")
                    
                    st.text_area(
                        "Formatted Text",
                        result.get("formatted_text", ""),
                        height=300,
                        disabled=True
                    )

                    pdf_base64 = result.get("pdf_base64")
                    if pdf_base64:
                        pdf_bytes = base64.b64decode(pdf_base64)
                        display_pdf_preview(pdf_bytes, height=600)
                        st.divider()
                        st.download_button(
                            "⬇️ Download Formatted Text",
                            result.get("formatted_text", ""),
                            file_name=f"formatted_{uploaded_file.name.replace('.pdf', '.txt')}",
                            mime="text/plain"
                        )
                    else:
                        st.warning("PDF output unavailable.")
                else:
                    display_error(response)


# ================= CONVERT TO PDF =================
elif menu == "🔄 Convert Other Files to PDF":
    st.header("🔄 Convert Files to PDF")
    st.write("Convert various file formats to PDF")
    
    uploaded_file = st.file_uploader(
        "📤 Upload File",
        type=["docx", "pptx", "txt", "jpg", "png", "json", "xml"],
        key="convert_to_pdf_upload"
    )
    
    if uploaded_file:
        st.success(f"✅ File uploaded: {uploaded_file.name}")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("File Type", uploaded_file.type or "Unknown")
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
                
                if success and "application/pdf" in response.headers.get("content-type", ""):
                    display_success("✅ File converted to PDF!")
                    base_name = os.path.splitext(uploaded_file.name)[0]
                    st.download_button(
                        "⬇️ Download PDF",
                        response.content,
                        file_name=f"{base_name}.pdf",
                        mime="application/pdf"
                    )
                else:
                    display_error("Conversion failed")

# ================= CONVERT FROM PDF =================
elif menu == "🔄 Convert PDF to Other Files":
    st.header("🔄 Convert PDF to Other Formats")
    st.write("Export PDF to various file formats")
    
    uploaded_file = st.file_uploader(
        "📤 Upload PDF",
        type=["pdf"],
        key="convert_from_pdf_upload"
    )
    
    if uploaded_file:
        st.success(f"✅ PDF uploaded: {uploaded_file.name}")
        
        st.metric("File Size", f"{uploaded_file.size / 1024:.2f} KB")
        
        col1, col2 = st.columns(2)
        with col1:
            output_format = st.selectbox(
                "Select Output Format",
                ["Word (.docx)", "Text (.txt)", "Image (.png)", "CSV", "JSON", "Excel (.xlsx)"]
            )
        
        with col2:
            if output_format == "Image (.png)":
                st.info("Save as images")
        
        if st.button("🔄 Convert PDF"):
            if not api_status:
                display_error("API Server is offline")
            else:
                with st.spinner(f"🔄 Converting to {output_format}..."):
                    format_map = {
                        "Word (.docx)": "docx",
                        "Text (.txt)": "txt",
                        "Image (.png)": "png",
                        "CSV": "csv",
                        "JSON": "json",
                        "Excel (.xlsx)": "xlsx"
                    }
                    
                    success, response = safe_api_call(
                        "/convert-from-pdf",
                        files={"file": uploaded_file},
                        data={"format": format_map.get(output_format, "txt")}
                    )
                
                if success:
                    display_success(f"✅ PDF converted to {output_format}!")
                    base_name = os.path.splitext(uploaded_file.name)[0]
                    
                    ext_map = {
                        "Word (.docx)": ".docx",
                        "Text (.txt)": ".txt",
                        "Image (.png)": ".png",
                        "CSV": ".csv",
                        "JSON": ".json",
                        "Excel (.xlsx)": ".xlsx"
                    }
                    
                    mime_map = {
                        "Word (.docx)": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "Text (.txt)": "text/plain",
                        "Image (.png)": "image/png",
                        "CSV": "text/csv",
                        "JSON": "application/json",
                        "Excel (.xlsx)": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    }
                    
                    st.download_button(
                        f"⬇️ Download {output_format}",
                        response.content,
                        file_name=f"{base_name}{ext_map.get(output_format, '.txt')}",
                        mime=mime_map.get(output_format, "text/plain")
                    )
                else:
                    display_error("Conversion failed")

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
                ["Short (50 words)", "Medium (150 words)", "Long (300 words)"],
                key="summary_length"
            )
        
        with col2:
            summary_type = st.selectbox(
                "Summary Type",
                ["Overview", "Key Points", "Detailed"]
            )
        
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
                    
                    tabs = st.tabs(["📌 Summary", "🔑 Key Points", "📊 Statistics"])
                    
                    with tabs[0]:
                        st.write(data.get("summary", "No summary available"))
                    
                    with tabs[1]:
                        key_points = data.get("key_points", [])
                        if isinstance(key_points, list):
                            for i, point in enumerate(key_points, 1):
                                st.write(f"{i}. {point}")
                        else:
                            st.write(key_points)
                    
                    with tabs[2]:
                        stats = data.get("statistics", {})
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Pages", stats.get("pages", "N/A"))
                        with col2:
                            st.metric("Words", stats.get("words", "N/A"))
                        with col3:
                            st.metric("Compression", stats.get("compression_ratio", "N/A"))
                    
                    summary_text = data.get("summary", "")
                    
                    # Generate a downloadable PDF for the summary
                    try:
                        from fpdf import FPDF
                        pdf = FPDF(unit="pt", format="letter")
                        pdf.add_page()
                        pdf.set_font("Helvetica", size=14)
                        pdf.multi_cell(0, 20, text=f"Document Summary: {uploaded_file.name}")
                        pdf.ln(10)
                        
                        pdf.set_font("Helvetica", size=11)
                        # Filter to standard printable chars to avoid Helvetica rendering crash
                        safe_summary = str(summary_text).encode("latin-1", "replace").decode("latin-1")
                        pdf.multi_cell(0, 15, text=safe_summary)
                        
                        key_points_text = data.get("key_points", "")
                        if key_points_text:
                            pdf.ln(20)
                            pdf.set_font("Helvetica", size=14)
                            pdf.multi_cell(0, 20, text="Key Points")
                            pdf.ln(10)
                            pdf.set_font("Helvetica", size=11)
                            
                            safe_key = str(key_points_text).encode("latin-1", "replace").decode("latin-1")
                            pdf.multi_cell(0, 15, text=safe_key)
                        
                        pdf_bytes = bytes(pdf.output())
                        
                        st.download_button(
                            "⬇️ Download Summary (PDF)",
                            data=pdf_bytes,
                            file_name=f"summary_{uploaded_file.name.replace('.pdf', '')}.pdf",
                            mime="application/pdf",
                            key="download_summary_pdf"
                        )
                    except Exception as e:
                        # Fallback to Text download
                        st.download_button(
                            "⬇️ Download Summary",
                            summary_text,
                            file_name=f"summary_{uploaded_file.name.replace('.pdf', '')}.txt",
                            mime="text/plain"
                        )
                else:
                    display_error(response)


# ================= TRANSLATE PDF =================
elif menu == "🌍 Translate PDF":
    st.header("🌍 Translate PDF")
    st.write("Translate PDF content to multiple languages")
    
    uploaded_file = st.file_uploader(
        "📤 Upload PDF",
        type=["pdf"],
        key="translate_upload"
    )
    
    if uploaded_file:
        st.success(f"✅ PDF uploaded: {uploaded_file.name}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            source_language = st.selectbox(
                "Source Language",
                ["English", "Hindi", "Gujarati", "French", "Spanish", "German"],
                key="source_lang"
            )
        
        with col2:
            target_language = st.selectbox(
                "Target Language",
                ["Select", "Hindi", "English", "French", "Spanish", "Gujarati", "German"],
                key="target_lang"
            )
        
        if st.button("🌐 Translate PDF"):
            if target_language == "Select":
                st.warning("⚠️ Please select a target language")
            elif not api_status:
                display_error("API Server is offline")
            else:
                with st.spinner(f"⏳ Translating to {target_language}..."):
                    files = {
                        "file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")
                    }
                    
                    payload = {
                        "target_language": target_language,
                        "source_language": source_language
                    }
                    
                    success, response = safe_api_call(
                        "/translate-pdf",
                        files=files,
                        data=payload
                    )
                
                if success:
                    data = response.json()
                    target_lang = data.get("target_language", target_language)
                    display_success(f"✅ Successfully translated to {target_lang}!")
                    
                    pdf_base64 = data.get("pdf_base64")
                    if pdf_base64:
                        tabs = st.tabs(["📝 Translation", "📊 Details", "📥 Download"])
                    else:
                        tabs = st.tabs(["📝 Translation", "📊 Details", "📥 Download"])
                    
                    with tabs[0]:
                        st.text_area(
                            "Translated Text",
                            data.get("translated_text", ""),
                            height=400,
                            disabled=True
                        )
                    
                    with tabs[1]:
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Source", data.get("source_language", "N/A"))
                        with col2:
                            st.metric("Target", data.get("target_language", "N/A"))
                        with col3:
                            st.metric("Status", "✅ Complete")
                        
                        if data.get("note"):
                            st.info(f"ℹ️ {data.get('note')}")
                    
                    with tabs[2]:
                        if pdf_base64:
                            pdf_bytes = base64.b64decode(pdf_base64)
                            display_pdf_preview(pdf_bytes, height=600)
                            st.divider()
                            st.download_button(
                                "⬇️ Download Translated PDF",
                                pdf_bytes,
                                file_name=f"{os.path.splitext(uploaded_file.name)[0]}_{target_language.lower()}_translation.pdf",
                                mime="application/pdf",
                                key="translate_pdf_download_btn"
                            )
                        
                        st.download_button(
                            "⬇️ Download Translated Text",
                            data.get("translated_text", ""),
                            file_name=f"{os.path.splitext(uploaded_file.name)[0]}_{target_language.lower()}_translation.txt",
                            mime="text/plain",
                            key="translate_text_download"
                        )
                        
                        if not pdf_base64:
                            st.caption("PDF preview/download was not generated for this response, but translated text is still available below.")
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
