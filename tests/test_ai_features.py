import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from backend.main import app
from modules.blank_detector import find_blank_in_file
from modules.error_detector import detect_errors
from modules.error_solver import generate_corrected_pdf
from modules.summarizer import summarize_text

client = TestClient(app)


def _create_sample_pdf(pdf_path, text="This is a sample PDF with a error for testing."):
    pdf = canvas.Canvas(str(pdf_path))
    pdf.drawString(72, 720, text)
    pdf.save()


def _workspace_temp_dir():
    base_dir = Path("tests_runtime") / f"case_{uuid.uuid4().hex}"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def test_detect_errors_simple():
    text = "This is a test sentence with a error."
    result = detect_errors(text)
    assert isinstance(result, str)
    assert result.strip()


def test_summarize_text():
    text = (
        "Python is a programming language. "
        "It is widely used for scripting, data science, and web development. "
        "It is also popular for automation."
    )
    summary = summarize_text(text, "short")
    assert isinstance(summary, str)
    assert summary.strip()


def test_find_blank_fields_no_pdf():
    temp_dir = _workspace_temp_dir()
    pdf_path = temp_dir / "simple.pdf"
    _create_sample_pdf(pdf_path, "No blanks in this file.")

    blanks = find_blank_in_file(str(pdf_path))
    assert isinstance(blanks, dict)
    assert "message" in blanks or "form_fields" in blanks


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "status" in resp.json()


def test_error_detector_endpoint():
    temp_dir = _workspace_temp_dir()
    pdf_path = temp_dir / "upload.pdf"
    _create_sample_pdf(pdf_path)

    with open(pdf_path, "rb") as file_handle:
        resp = client.post("/error-detector", files={"file": ("upload.pdf", file_handle, "application/pdf")})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "errors" in data
    assert "metadata" in data


def test_convert_from_pdf_to_text():
    temp_dir = _workspace_temp_dir()
    pdf_path = temp_dir / "convert.pdf"
    _create_sample_pdf(pdf_path, "Convert this PDF to plain text.")

    with open(pdf_path, "rb") as file_handle:
        resp = client.post(
            "/convert-from-pdf",
            files={"file": ("convert.pdf", file_handle, "application/pdf")},
            data={"format": "txt"},
        )

    assert resp.status_code == 200
    assert resp.content


def test_generate_hindi_pdf():
    output_path = _workspace_temp_dir() / "hindi_translation.pdf"
    result = generate_corrected_pdf(
        "यह एक परीक्षण दस्तावेज़ है। हिंदी पीडीएफ डाउनलोड काम करना चाहिए।",
        str(output_path),
    )

    assert result == str(output_path)
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_generate_gujarati_pdf():
    output_path = _workspace_temp_dir() / "gujarati_translation.pdf"
    result = generate_corrected_pdf(
        "આ એક પરીક્ષણ દસ્તાવેજ છે. ગુજરાતી પીડીએફ ડાઉનલોડ કામ કરવું જોઈએ.",
        str(output_path),
    )

    assert result == str(output_path)
    assert output_path.exists()
    assert output_path.stat().st_size > 0
