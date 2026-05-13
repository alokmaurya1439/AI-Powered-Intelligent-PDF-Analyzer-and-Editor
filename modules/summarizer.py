"""
Summarizer Module — works with or without a Groq API key.
Without API key: uses extractive summarization (TF-IDF sentence scoring).
With API key: uses Groq LLM for abstractive summarization.
"""
import os
import re
import math
import logging
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
client: Optional[object] = None

if GROQ_API_KEY and GROQ_API_KEY != "your_groq_api_key_here":
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        logging.info("✅ Groq summarizer client initialized")
    except Exception as e:
        logging.warning(f"Groq init failed: {e}")

_CHUNK_SIZE  = 15000
_MAX_WORKERS = 5
MODEL_PRIMARY  = "llama-3.3-70b-versatile"
MODEL_FALLBACK = "llama-3.1-8b-instant"


# ─────────────────────────────────────────────
# EXTRACTIVE SUMMARIZATION (no API needed)
# ─────────────────────────────────────────────
def _extractive_summary(text: str, target_sentences: int = 8) -> str:
    """TF-IDF based extractive summarization — works offline."""
    # Clean and split into sentences
    text = re.sub(r'\s+', ' ', text).strip()
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    if not sentences:
        return text[:500]
    if len(sentences) <= target_sentences:
        return " ".join(sentences)

    # Build word frequency (TF)
    stop_words = {
        'the','a','an','and','or','but','in','on','at','to','for','of','with',
        'is','are','was','were','be','been','being','have','has','had','do',
        'does','did','will','would','could','should','may','might','shall',
        'this','that','these','those','it','its','i','we','you','he','she',
        'they','their','our','your','his','her','from','by','as','not','no',
        'so','if','then','than','also','just','more','about','up','out','into'
    }

    word_freq: dict = {}
    for sent in sentences:
        for word in re.findall(r'\b[a-zA-Z]{3,}\b', sent.lower()):
            if word not in stop_words:
                word_freq[word] = word_freq.get(word, 0) + 1

    # IDF weighting
    n = len(sentences)
    idf: dict = {}
    for word in word_freq:
        doc_count = sum(1 for s in sentences if word in s.lower())
        idf[word] = math.log((n + 1) / (doc_count + 1)) + 1

    # Score each sentence
    scores = []
    for i, sent in enumerate(sentences):
        words = re.findall(r'\b[a-zA-Z]{3,}\b', sent.lower())
        if not words:
            scores.append(0)
            continue
        score = sum(word_freq.get(w, 0) * idf.get(w, 1) for w in words if w not in stop_words)
        score /= len(words)
        # Boost first and last sentences slightly
        if i < 3:
            score *= 1.3
        if i >= len(sentences) - 3:
            score *= 1.1
        scores.append(score)

    # Pick top N sentences, preserve original order
    indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    top_indices = sorted([idx for idx, _ in indexed[:target_sentences]])
    return " ".join(sentences[i] for i in top_indices)


def _extractive_keypoints(text: str, n: int = 8) -> str:
    """Extract key sentences as bullet points."""
    text = re.sub(r'\s+', ' ', text).strip()
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 30]

    if not sentences:
        return "• " + text[:200]

    # Score by length and keyword density
    scored = []
    for s in sentences:
        words = s.split()
        # Prefer medium-length sentences (not too short, not too long)
        length_score = min(len(words), 30) / 30.0
        # Prefer sentences with numbers or proper nouns
        has_number = bool(re.search(r'\d', s))
        has_caps = len(re.findall(r'\b[A-Z][a-z]+', s)) > 1
        score = length_score + (0.3 if has_number else 0) + (0.2 if has_caps else 0)
        scored.append((score, s))

    scored.sort(reverse=True)
    top = [s for _, s in scored[:n]]
    return "\n".join(f"• {s}" for s in top)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _split(text: str, chunk_size: int = _CHUNK_SIZE) -> List[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) + 1 <= chunk_size:
            current += s + " "
        else:
            if current:
                chunks.append(current.strip())
            if len(s) > chunk_size:
                for i in range(0, len(s), chunk_size):
                    chunks.append(s[i:i + chunk_size])
                current = ""
            else:
                current = s + " "
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text]


def _normalize_length(length: str) -> tuple:
    """Returns (word_target_str, target_sentences) for the given length label."""
    l = length.lower()
    if "short" in l or "100" in l:
        return "approximately 80-100 words", 5
    if "long" in l or "500" in l:
        return "approximately 400-500 words", 15
    return "approximately 200-250 words", 8   # medium default


# ─────────────────────────────────────────────
# LLM CALLS (Groq)
# ─────────────────────────────────────────────
def _call_summarize(chunk: str, word_target: str) -> str:
    prompt = (
        f"Summarize the following text clearly and concisely.\n"
        f"Target length: {word_target}.\n"
        f"Return ONLY the summary text, no headings or labels.\n\n"
        f"TEXT:\n{chunk}"
    )
    for model in [MODEL_PRIMARY, MODEL_FALLBACK]:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=700,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                logging.warning(f"Rate limit on {model}, trying fallback")
                continue
            raise
    raise RuntimeError("All models rate-limited")


def _call_keypoints(chunk: str) -> str:
    prompt = (
        "Extract the key points from the text below.\n"
        "Return bullet points only, one per line starting with •.\n"
        "Each bullet point must be on its own separate line.\n"
        "Add a blank line between each bullet point.\n"
        "No headings, no extra text.\n\n"
        f"TEXT:\n{chunk}"
    )
    for model in [MODEL_PRIMARY, MODEL_FALLBACK]:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=800,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                logging.warning(f"Rate limit on {model}, trying fallback")
                continue
            raise
    raise RuntimeError("All models rate-limited")


# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────
def summarize_text(text: str, length: str = "Medium (250 words)") -> str:
    if not isinstance(text, str) or not text.strip():
        return "⚠ No text could be extracted from this PDF."

    word_target, target_sentences = _normalize_length(length)

    # ── Offline extractive fallback ──────────────────────────────────
    if client is None:
        logging.info("summarize_text: using extractive (no API key)")
        return _extractive_summary(text, target_sentences=target_sentences)

    # ── LLM summarization ────────────────────────────────────────────
    chunks = _split(text)
    logging.info(f"summarize_text: {len(chunks)} chunks, target={word_target}")

    results = [""] * len(chunks)
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(chunks))) as ex:
        future_map = {ex.submit(_call_summarize, c, word_target): i for i, c in enumerate(chunks)}
        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                logging.error(f"summarize chunk {idx} failed: {e}")
                results[idx] = _extractive_summary(chunks[idx], target_sentences=3)

    combined = "\n\n".join(r for r in results if r)

    # Consolidate multiple chunks into one final summary
    if len(chunks) > 1:
        try:
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{
                    "role": "user",
                    "content": (
                        f"Consolidate these section summaries into one coherent summary.\n"
                        f"Target length: {word_target}.\n"
                        f"Return ONLY the final summary text.\n\n{combined}"
                    )
                }],
                temperature=0.3,
                max_tokens=700,
            )
            content = resp.choices[0].message.content
            if content and content.strip():
                return content.strip()
        except Exception as e:
            logging.error(f"consolidation error: {e}")

    return combined


def extract_key_points(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return "⚠ No text could be extracted from this PDF."

    # ── Offline extractive fallback ──────────────────────────────────
    if client is None:
        logging.info("extract_key_points: using extractive (no API key)")
        return _extractive_keypoints(text)

    # ── LLM key points ───────────────────────────────────────────────
    chunks = _split(text)
    logging.info(f"extract_key_points: {len(chunks)} chunks")

    results = [""] * len(chunks)
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(chunks))) as ex:
        future_map = {ex.submit(_call_keypoints, c): i for i, c in enumerate(chunks)}
        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                logging.error(f"keypoints chunk {idx} failed: {e}")
                results[idx] = _extractive_keypoints(chunks[idx], n=3)

    # Join chunks with double newline so bullets are separated
    combined = "\n\n".join(r for r in results if r)

    # Normalise: ensure every bullet line is separated by a blank line
    lines = combined.splitlines()
    normalised = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        normalised.append(stripped)
        normalised.append("")   # blank line after every bullet

    return "\n".join(normalised).strip()
