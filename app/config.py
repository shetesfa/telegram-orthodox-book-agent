import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Root Directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env if it exists
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()

# App Directories
DATA_DIR = BASE_DIR / "data"
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", str(DATA_DIR / "downloads")))
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "database" / "books.db")))
LOGS_DIR = BASE_DIR / "logs"
SESSION_PATH = Path(os.getenv("SESSION_NAME", str(DATA_DIR / "telegram_user_session")))

# Ensure directories exist
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Logging Setup (Strictly avoiding secrets)
LOG_FILE = LOGS_DIR / "app.log"
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("telegram_book_agent")

# Telegram Configuration
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "").strip()
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE", "").strip()

# Gemini AI Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

# Default Settings
DEFAULT_SETTINGS = {
    "min_confidence": 90,
    "review_threshold": 70,
    "auto_send_high_confidence": True,
    "ask_uncertain": True,
    "skip_duplicates": True,
    "continue_after_errors": True,
    "delete_downloads_after_send": True,
    "max_file_size_mb": 500,
    "allowed_extensions": "pdf,epub,mobi,djvu",
    "search_limit_per_chat": 100,
    "weight_title": 60,
    "weight_author": 25,
    "weight_edition": 10,
    "weight_relevance": 5,
    "enable_global_search": True,
    "target_channel": "https://t.me/+2EsS9AQ1kt9mYmFk"
}
