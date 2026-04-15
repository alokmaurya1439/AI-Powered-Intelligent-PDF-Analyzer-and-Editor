from groq import Groq
import os
import logging
from typing import List
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

client = None
if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        logging.warning(f"Groq init failed: {e}")
        client = None

from concurrent.futures import ThreadPoolExecutor

# ================= TEXT CHUNKING =================
def split_text(text: str, chunk_size: int = 25000) -> List[str]:
    """Split text into large chunks for LLM."""
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


# ================= FALLBACK =================
def basic_summary(text: str) -> str:
    """Fallback summary if API fails."""
    sentences = text.split(".")
    return ". ".join(sentences[:3]).strip() + "..." if len(sentences) > 3 else text


def basic_keypoints(text: str) -> str:
    """Fallback key points extraction."""
    lines = text.split("\n")
    return "\n".join(f"• {line}" for line in lines[:5] if line.strip())


# ================= SUMMARIZE =================
def summarize_text(text: str, length: str = "Medium (150 words)") -> str:
    if not isinstance(text, str) or not text.strip():
        return "⚠ No valid text provided"

    if client is None:
        return basic_summary(text)

    chunks = split_text(text, chunk_size=25000)

    def _process_chunk(chunk):
        prompt = f"""
Summarize the following text clearly and concisely.
Target Summary Length: {length}

TEXT:
{chunk}
"""
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=400
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logging.error(f"Summarization error: {e}")
            return basic_summary(chunk)

    with ThreadPoolExecutor(max_workers=5) as executor:
        summaries = list(executor.map(_process_chunk, chunks))

    return "\n".join(filter(None, summaries))


# ================= KEY POINTS =================
def extract_key_points(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return "⚠ No valid text provided"

    if client is None:
        return basic_keypoints(text)

    chunks = split_text(text, chunk_size=25000)

    def _process_chunk(chunk):
        prompt = f"""
Extract key points from the text. Return bullet points only.

TEXT:
{chunk}
"""
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=400
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logging.error(f"Key point extraction error: {e}")
            return basic_keypoints(chunk)

    with ThreadPoolExecutor(max_workers=5) as executor:
        all_points = list(executor.map(_process_chunk, chunks))

    return "\n".join(filter(None, all_points))