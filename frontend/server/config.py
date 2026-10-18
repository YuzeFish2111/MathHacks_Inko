"""Paths, limits, and settings read from the environment or a .env file."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # frontend/
PROJECT_ROOT = ROOT.parent                             # the MathHacks repo
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data"
# The analysis backend's source. Inko reads its contract (schemas.py) and scoring curves
# (scoring_config.py) from here so the two can never drift apart.
BACKEND_APP_DIR = PROJECT_ROOT / "backend" / "app"


def _load_dotenv(path: Path) -> None:
    """Tiny .env reader so we don't need another dependency. Real env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")

# 5173 so it never clashes with the analysis backend on 8000 (and its CORS list already allows it).
PORT = int(os.environ.get("INKO_PORT") or 5173)
DB_PATH = Path(os.environ.get("INKO_DB_PATH") or DATA_DIR / "inko.db")

# The analysis backend (backend/, started with: cd backend && uvicorn app.main:app --reload)
ANALYSIS_API_URL = (os.environ.get("ANALYSIS_API_URL") or "http://127.0.0.1:8000").rstrip("/")
ANALYSIS_TIMEOUT_S = float(os.environ.get("ANALYSIS_TIMEOUT_S") or 120)   # the first OCR run is slow

# Uploads
MAX_UPLOAD_BYTES = 10 * 1024 * 1024   # matches the "under 10 MB" message
MAX_MODEL_SIDE = 2000                 # long side of the photo sent to the analysis backend
THUMB_SIDE = 360                      # long side of history thumbnails
