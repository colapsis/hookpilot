import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/hookpilot.db")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
MAX_BODY_SIZE = int(os.getenv("MAX_BODY_SIZE", str(512 * 1024)))  # 512 KB
REQUEST_RETENTION_DAYS = int(os.getenv("REQUEST_RETENTION_DAYS", "30"))
MAX_REQUESTS_PER_BUCKET = int(os.getenv("MAX_REQUESTS_PER_BUCKET", "500"))

# AI — set AI_MODEL to enable. Use any LiteLLM-compatible model string.
# Examples: "gpt-4o-mini", "claude-haiku-3-5-20251001", "gemini/gemini-2.0-flash",
#           "groq/llama-3.1-8b-instant", "ollama/llama3", "mistral/mistral-small-latest"
AI_MODEL = os.getenv("AI_MODEL", "")
