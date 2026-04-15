"""
File Format Converter Module
Handles conversion between PDF and various file formats
"""
import os
import re
import logging
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
import docx
import html2text
import markdown

logging.basicConfig(level=logging.INFO) 


class FileConverter:
    def __init__(self):
        self.supported_formats = {
            'pdf': ['docx', 'txt', 'html', 'md'],
            'docx': ['pdf', 'txt', 'html', 'md'],
            'txt': ['pdf', 'html', 'md'],
            'html': ['pdf', 'txt', 'md', 'docx'],
            'md': ['pdf', 'txt', 'html', 'docx']
        }

      # ================= COMMON =================
    def _check_file(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")

    def _create_pdf(self, text, output_path):
        """Reusable PDF generator"""
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        paragraphs = text.split('\n\n')

        for para in paragraphs:
            if para.strip():
                story.append(Paragraph(para.strip(), styles['Normal']))
                story.append(Spacer(1, 10))  

        doc.build(story)

    # ================= PDF → OTHER =================
    def pdf_to_docx(self, pdf_path, output_path):
        self._check_file(pdf_path)
        
        try:
            from pdf2docx import Converter
            cv = Converter(pdf_path)
            cv.convert(output_path)
            cv.close()
            return True
        except ImportError:
            logging.warning("pdf2docx not installed. Falling back to simple text.")
            from modules.pdf_reader import extract_text_from_pdf
            text = extract_text_from_pdf(pdf_path)

            doc = docx.Document()
            for para in text.split('\n\n'):
                if para.strip():
                    doc.add_paragraph(para.strip())

            doc.save(output_path)
            return True

    def pdf_to_txt(self, pdf_path, output_path):
        self._check_file(pdf_path)

        from modules.pdf_reader import extract_text_from_pdf
        text = extract_text_from_pdf(pdf_path)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)

        return True

    def pdf_to_html(self, pdf_path, output_path):
        self._check_file(pdf_path)
        import fitz
        html_content = "<!DOCTYPE html><html><head><meta charset='UTF-8'></head><body style='margin: 0; padding: 0'>"
        with fitz.open(pdf_path) as pdf:
            for page in pdf:
                try:
                    html_content += page.get_text("html")
                except Exception:
                    html_content += f"<p>{page.get_text('text')}</p>"
        html_content += "</body></html>"
                
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        return True

    def pdf_to_markdown(self, pdf_path, output_path):
        self._check_file(pdf_path)
        import fitz
        
        md = ""
        with fitz.open(pdf_path) as pdf:
            for page in pdf:
                blocks = page.get_text("blocks")
                blocks.sort(key=lambda b: (b[1], b[0]))
                for b in blocks:
                    block_text = b[4].strip()
                    if block_text:
                        md += block_text + "\n\n"

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md)

        return True

    # ================= OTHER → PDF =================
    def docx_to_pdf(self, docx_path, output_path):
        self._check_file(docx_path)

        doc = docx.Document(docx_path)
        text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())

        self._create_pdf(text, output_path)
        return True

    def txt_to_pdf(self, txt_path, output_path):
        self._check_file(txt_path)

        with open(txt_path, 'r', encoding='utf-8') as f:
            text = f.read()

        self._create_pdf(text, output_path)
        return True

    def html_to_pdf(self, html_path, output_path):
        self._check_file(html_path)

        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        h = html2text.HTML2Text()
        h.ignore_links = False
        text = h.handle(html_content)

        self._create_pdf(text, output_path)
        return True

    def markdown_to_pdf(self, md_path, output_path):
        self._check_file(md_path)

        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()

        html = markdown.markdown(md_content)
        text = re.sub(r'<[^>]+>', '', html)

        self._create_pdf(text, output_path)
        return True

    # ================= MAIN =================
    def convert_file(self, input_path, output_path, from_format, to_format):
        from_format = from_format.lower()
        to_format = to_format.lower()

        if from_format not in self.supported_formats:
            raise ValueError(f"Unsupported format: {from_format}")

        if to_format not in self.supported_formats[from_format]:
            raise ValueError(f"Conversion {from_format} → {to_format} not supported")

        method_name = f"{from_format}_to_{to_format}"

        if hasattr(self, method_name):
            logging.info(f"Converting {from_format} → {to_format}")
            return getattr(self, method_name)(input_path, output_path)

        raise Exception("Conversion method not implemented")

    # ================= MIME =================
    def get_mime_type(self, format_type):
        return {
            'pdf': 'application/pdf',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'txt': 'text/plain',
            'html': 'text/html',
            'md': 'text/markdown'
        }.get(format_type, 'application/octet-stream')


# Global instance
file_converter = FileConverter()