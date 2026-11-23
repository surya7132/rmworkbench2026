"""Settings. Everything can be overridden with environment variables."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("COMPASS_DB", ROOT / "data" / "compass.db"))
SECRET_KEY = os.environ.get("COMPASS_SECRET", "dev-only-change-me-before-sharing")
DEMO_PASSWORD = "Demo@2026"
PAGE_SIZE = 25
UPLOAD_DIR = Path(os.environ.get("COMPASS_UPLOADS", ROOT / "data" / "uploads"))   # reports uploaded on the Spreading screen
MAX_UPLOAD_MB = 25
