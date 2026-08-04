"""Central configuration, driven by environment variables."""
import os


def _csv(name):
    return [x.strip() for x in os.environ.get(name, "").split(",") if x.strip()]


# --- Telegram ---
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")  # only this chat can run admin cmds

# --- Agent (Anthropic) ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("NEWS_MODEL", "claude-haiku-4-5-20251001")

# --- Scheduling / behavior ---
DB_PATH = os.environ.get("NEWS_DB_PATH", "/data/news.db")
TIMEZONE = os.environ.get("NEWS_TZ", "America/Sao_Paulo")
DIGEST_TIME = os.environ.get("NEWS_DIGEST_TIME", "07:00")   # HH:MM in TIMEZONE
POLL_TIMEOUT = int(os.environ.get("NEWS_POLL_TIMEOUT", "30"))  # long-poll seconds
MAX_CANDIDATES = int(os.environ.get("NEWS_MAX_CANDIDATES", "40"))
MAX_DIGEST = int(os.environ.get("NEWS_MAX_DIGEST", "6"))
ENABLE_SHORTS = os.environ.get("NEWS_ENABLE_SHORTS", "false").lower() in ("1", "true", "yes")

INCLUDE = _csv("NEWS_INCLUDE")
EXCLUDE = _csv("NEWS_EXCLUDE")

# --- Sources ---
FEEDS = {
    "Hacker News": "https://hnrss.org/frontpage",
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
    "TechCrunch": "https://techcrunch.com/feed/",
}
