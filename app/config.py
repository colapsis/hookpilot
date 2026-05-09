import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/hookpilot.db")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
MAX_BODY_SIZE = int(os.getenv("MAX_BODY_SIZE", str(512 * 1024)))  # 512 KB
REQUEST_RETENTION_DAYS = int(os.getenv("REQUEST_RETENTION_DAYS", "30"))
MAX_REQUESTS_PER_BUCKET = int(os.getenv("MAX_REQUESTS_PER_BUCKET", "500"))
