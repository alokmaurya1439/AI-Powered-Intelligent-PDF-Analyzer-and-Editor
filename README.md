# AI Smart PDF Editor

An intelligent PDF editing application that uses AI to process and enhance PDF documents with advanced features for text extraction, error detection, translation, summarization, and format conversion.

## Project Structure

```
AI-Smart-PDF-Editor/
├── frontend/
│   └── app.py                  # Streamlit web interface
├── backend/
│   ├── main.py                 # FastAPI backend server
│   ├── api.py                  # API routes and endpoints
│   └── __init__.py             # Backend package init
├── modules/
│   ├── pdf_reader.py           # PDF text extraction with OCR support
│   ├── pdf_editor.py           # PDF creation and editing
│   ├── ocr_engine.py           # Hybrid OCR engine (Tesseract + PyMuPDF)
│   ├── error_detector.py       # Text quality and error detection
│   ├── error_solver.py         # Text correction and improvement
│   ├── summarizer.py           # Text summarization and key point extraction
│   ├── translate.py            # AI-powered translation
│   ├── file_converter.py       # Format conversion utilities
│   ├── blank_detector.py       # Form blank field detection
│   └── __init__.py             # Modules package init
├── uploads/                     # Temporary uploaded files storage
├── outputs/                     # Processed files output directory
├── temp/                        # Temporary processing directory
├── tests/                       # Test files
├── .env                         # Environment variables (create from .env.example)
├── .env.example                 # Environment variables template
├── requirements.txt             # Python dependencies
├── run.py                       # Main startup script
├── PROJECT_REPORT.md            # Project documentation
└── README.md                    # This file
```

## Features

### 📄 PDF Processing
- **Error Detection**: Detect grammar, spelling, punctuation, and semantic errors
- **Text Correction**: AI-powered text correction and improvement
- **Formatting Fix**: Apply professional formatting standards
- **Smart Form Filling**: Detect blank form fields and suggest auto-filling

### 🔄 Format Conversion
- **PDF ↔ DOCX**: Bidirectional conversion
- **PDF ↔ TXT**: Text extraction and PDF creation
- **PDF ↔ HTML**: Web format conversion
- **PDF ↔ Markdown**: Document markup conversion
- **Multi-format Support**: Handle DOCX, TXT, HTML, MD, Image formats

### 🤖 AI-Powered Features
- **Text Summarization**: Extract key points and create concise summaries
- **Translation**: Multilingual translation support (English, Hindi, French, Spanish, Gujarati, German, etc.)
- **Writing Enhancement**: Improve writing quality, clarity, and engagement
- **Quality Analysis**: Comprehensive text quality metrics and warnings
- **Metadata Extraction**: Get detailed PDF metadata information

### 🎯 Advanced Capabilities
- **Hybrid OCR**: Automatic OCR detection for scanned PDFs
- **Parallel Processing**: Efficient multi-page processing
- **Layout Preservation**: Maintain document structure during editing
- **Error Recovery**: Robust error handling with fallback mechanisms

## Installation

### Prerequisites
- Python 3.8+
- Tesseract OCR (for scanned PDF support)
  - **Windows**: Download from https://github.com/UB-Mannheim/tesseract/wiki
  - **Linux**: `sudo apt-get install tesseract-ocr`
  - **Mac**: `brew install tesseract`

### Step 1: Clone/Download the Project
```bash
git clone <repository-url>
cd AI-Smart-PDF-Editor
```

### Step 2: Create Virtual Environment
```bash
python -m venv myenv
```

### Step 3: Activate Virtual Environment
- **Windows**: `myenv\Scripts\activate`
- **Linux/Mac**: `source myenv/bin/activate`

### Step 4: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 5: Configure Environment
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` and add your API keys:
   ```
   GROQ_API_KEY=your_groq_api_key_here
   ```
   Get your Groq API key from: https://console.groq.com

## Configuration

### Required Environment Variables
- `GROQ_API_KEY`: Your Groq API key (required for AI features)
- `TESSERACT_PATH`: Path to Tesseract executable (for OCR)

### Optional Environment Variables
- `BACKEND_HOST`: Backend server host (default: 127.0.0.1)
- `BACKEND_PORT`: Backend server port (default: 8000)
- `FRONTEND_PORT`: Streamlit port (default: 8501)
- `DEBUG`: Debug mode (default: False)
- `LOG_LEVEL`: Logging level (default: INFO)

## Usage

### Option 1: Quick Start with run.py
```bash
python run.py
```
This will start both backend and frontend automatically.

### Option 2: Manual Start

**Terminal 1 - Start Backend**:
```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 - Start Frontend**:
```bash
streamlit run frontend/app.py
```

The application will be available at: `http://localhost:8501`

### API Endpoints

#### Text Processing
- `POST /error_detector` - Detect errors in PDF
- `POST /corrected-pdf` - Generate corrected PDF
- `POST /improve-writing` - Improve writing quality
- `POST /fix-formatting` - Apply formatting standards
- `POST /summarizer` - Summarize PDF content
- `POST /translate_pdf` - Translate PDF to target language

#### File Operations
- `POST /pdf-edit` - Extract PDF for editing
- `POST /form-filling` - Detect form blank fields
- `POST /convert-to-pdf` - Convert files to PDF
- `POST /convert-pdf-to` - Convert PDF to other formats
- `POST /process` - Main PDF processing endpoint

#### System
- `GET /` - Health check
- `GET /health` - Detailed health status

## Usage Examples

### 1. Error Detection & Correction
```
1. Upload PDF → "⚠️ Detect Errors"
2. View detected errors and quality analysis
3. Click "Generate Corrected PDF"
4. Download the corrected document
```

### 2. PDF Translation
```
1. Upload PDF → "🌍 Translate PDF"
2. Select target language
3. Click "Translate PDF"
4. Download translated text
```

### 3. Summarization
```
1. Upload PDF → "🤖 Summarize PDF"
2. Click "Summarizer"
3. View summary and key points
4. Copy or download results
```

### 4. Format Conversion
```
1. Upload PDF → "🔄 Convert PDF to Other Files"
2. Select target format (Word, Text, HTML, etc.)
3. Download converted file
```

### 5. Writing Improvement
```
1. Upload PDF → "✍ Improve Writing"
2. Click "Improve Writing"
3. View improved text
4. Download enhanced document
```

## Dependencies

### Core Libraries
- **fastapi**: Web framework for backend API
- **streamlit**: Web interface framework
- **uvicorn**: ASGI server
- **python-dotenv**: Environment variable management

### PDF Processing
- **fitz (PyMuPDF)**: PDF manipulation and text extraction
- **pypdf/PyPDF2**: PDF reading and manipulation
- **pdfplumber**: Advanced PDF text extraction
- **pytesseract**: Tesseract OCR wrapper
- **reportlab**: PDF generation from scratch

### AI & NLP
- **groq**: Groq API client for AI processing
- **transformers**: NLP models (optional)
- **torch**: Deep learning framework (optional)

### File Conversion
- **python-docx**: DOCX file handling
- **html2text**: HTML to text conversion
- **markdown**: Markdown processing

## Architecture

### Modular Design
```
┌─────────────────────────────────────────┐
│         Streamlit Frontend              │
│    (frontend/app.py)                    │
└────────────────┬────────────────────────┘
                 │
         HTTP Requests (REST API)
                 │
┌────────────────▼────────────────────────┐
│      FastAPI Backend                    │
│  (backend/main.py, backend/api.py)      │
└────────────────┬────────────────────────┘
                 │
    ┌────────────┴──────────────┐
    │                           │
    ▼                           ▼
┌─────────────────────┐   ┌──────────────────┐
│  Processing         │   │  File Operations │
│  Modules            │   │  Modules         │
├─────────────────────┤   ├──────────────────┤
│ • error_detector    │   │ • file_converter │
│ • error_solver      │   │ • blank_detector │
│ • summarizer        │   │ • pdf_editor     │
│ • translate         │   │ • pdf_reader     │
│ • ocr_engine        │   │ • ocr_engine     │
└─────────────────────┘   └──────────────────┘
         │
         ▼
    ┌──────────────────┐
    │ External APIs    │
    ├──────────────────┤
    │ • Groq LLM       │
    │ • Tesseract OCR  │
    └──────────────────┘
```

## Troubleshooting

### Issue: "GROQ_API_KEY not found"
**Solution**: Ensure `.env` file exists with your GROQ_API_KEY set.

### Issue: "Tesseract not found"
**Solution**: 
1. Install Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki
2. Update `TESSERACT_PATH` in `.env`

### Issue: Module import errors
**Solution**: Reinstall dependencies
```bash
pip install --upgrade -r requirements.txt
```

### Issue: Port already in use
**Solution**: Change port in `.env` or use:
```bash
uvicorn backend.main:app --port 8001
streamlit run frontend/app.py --server.port 8502
```

## Development

### Adding New Features
1. Create/edit module in `modules/` directory
2. Add API endpoint in `backend/api.py`
3. Add UI component in `frontend/app.py`
4. Update `.env` if new variables needed
5. Test thoroughly

### Running Tests
```bash
python -m pytest tests/
```

### Code Quality
```bash
# Format code
black modules/ backend/ frontend/

# Lint
pylint modules/ backend/ frontend/
```

## Performance Tips

1. **Large PDFs**: Enable parallel processing for OCR
2. **Translation**: Use smaller chunk sizes for better accuracy
3. **Memory**: Monitor memory usage for multi-page documents
4. **API Calls**: Implement rate limiting for external APIs

## Security Considerations

- Never commit `.env` file with real API keys
- Use environment variables for sensitive data
- Validate all file uploads
- Implement authentication for production
- Use HTTPS in production
- Sanitize user inputs

## Future Enhancements

- [ ] User authentication & authorization
- [ ] Batch processing support
- [ ] Advanced PDF annotation
- [ ] Real-time collaboration
- [ ] Cloud storage integration
- [ ] Additional language models
- [ ] Performance optimizations
- [ ] Docker containerization
- [ ] CI/CD pipeline
- [ ] Mobile app support

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

[Specify your license here]

## Support

For issues, questions, or suggestions:
1. Check the troubleshooting section
2. Review PROJECT_REPORT.md for detailed documentation
3. Create an issue on GitHub
4. Contact the development team

## Changelog

### Version 1.0.0
- Initial release
- Core PDF processing features
- Multi-format conversion support
- AI-powered text enhancement
- OCR capabilities for scanned documents

---

**Last Updated**: March 2026
**Status**: Active Development
