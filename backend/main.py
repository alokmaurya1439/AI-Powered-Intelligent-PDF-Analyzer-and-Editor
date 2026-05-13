# backend/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api import router

# ================= APP INIT =================
app = FastAPI(
    title="AI Smart PDF Editor API",
    description="Backend API for AI PDF tools: edit, OCR, convert, summarize, translate, detect errors",
    version="1.0.0",
)

# ── Increase multipart form field size limit to 50 MB ────────────────────────
# Default Starlette limit is 1 MB per field — too small for base64 signature images.
from starlette.formparsers import MultiPartParser
MultiPartParser.max_part_size = 50 * 1024 * 1024   # 50 MB per field

# ================= CORS =================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*"  # remove in production or lock to your exact domains
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= ROUTES =================
app.include_router(router)

# ================= HEALTH CHECK =================
@app.get("/", tags=["Health"])
def home():
    """
    Basic root endpoint to verify backend is running.
    """
    return {"message": "Backend running 🚀"}

@app.get("/health", tags=["Health"])
def health_check():
    """
    Liveness/readiness health check.
    """
    return {"status": "ok"}


# ================= RUN Uvicorn (for direct python backend/main.py) =================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        workers=1,
        log_level="info",
    )