import os
import re
import asyncio
import logging
from groq import Groq
from typing import List
from dotenv import load_dotenv


# ================= CONFIG =================
load_dotenv()
logging.basicConfig(level=logging.INFO)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MODEL_NAME = "llama-3.3-70b-versatile"
MAX_CHARS = 15000  # Dramatically increased to reduce API requests and massively speed up translation
MAX_CONCURRENT = 5  # Allow 5 concurrent chunk threads

# Safe client init
client = None
if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        logging.warning(f"Groq init failed: {e}")
        client = None


# ================= SPLIT TEXT =================
def split_text(text: str, max_chars: int = MAX_CHARS) -> List[str]:
    sentences = re.split(r'(?<=[.!?]) +', text)
    chunks, current = [], ""

    for sentence in sentences:
        if len(current) + len(sentence) < max_chars:
            current += sentence + " "
        else:
            chunks.append(current.strip())
            current = sentence + " "

    if current:
        chunks.append(current.strip())

    return chunks


# ================= CLEAN =================
def clean_translation(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("```", "")
            .replace("Translation:", "")
            .replace("\n\n\n", "\n\n")
            .strip()
    )


# ================= FALLBACK =================
def fallback_translate(text: str, target_lang: str) -> str:
    return f"[Translation unavailable → showing original]\n{text}"


# ================= API CALL =================
def call_groq_api(prompt: str) -> str:
    if client is None:
        raise Exception("Groq client unavailable")

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        max_tokens=1500,
        messages=[
            {"role": "system", "content": "You are a professional translator."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content


# ================= TRANSLATE CHUNK =================
async def translate_chunk(chunk: str, target_lang: str, sem: asyncio.Semaphore) -> str:
    async with sem:
        loop = asyncio.get_event_loop()

        prompt = f"""
Translate the following text into {target_lang}.

- Keep meaning accurate
- Maintain formatting
- Do NOT add explanation
- Return ONLY translated text

TEXT:
{chunk}
"""

        for attempt in range(2):  # retry mechanism
            try:
                result = await loop.run_in_executor(None, call_groq_api, prompt)
                return clean_translation(result)

            except Exception as e:
                logging.warning(f"Retry {attempt+1} failed: {e}")
                await asyncio.sleep(1)

        return fallback_translate(chunk, target_lang)


# ================= MAIN FUNCTION =================
async def translate_text(text: str, target_lang: str = "Hindi", source_lang: str | None = None) -> str:
    if not isinstance(text, str) or not text.strip():
        return "⚠️ No valid text provided."

    try:
        chunks = split_text(text)
        logging.info(f"Total chunks: {len(chunks)}")

        sem = asyncio.Semaphore(MAX_CONCURRENT)

        if source_lang:
            logging.info(f"Translating from {source_lang} to {target_lang}")

        tasks = [
            translate_chunk(chunk, target_lang, sem)
            for chunk in chunks
        ]

        results = await asyncio.gather(*tasks)

        return "\n\n".join(results)

    except Exception as e:
        logging.error(f"Translation failed: {e}")
        return f"❌ Translation failed: {str(e)}"