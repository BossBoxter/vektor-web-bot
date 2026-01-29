# src/config.py
import os


class Config:
    # Runtime
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    PORT = int(os.getenv("PORT", "8080"))

    # Telegram
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://vektor-web-bot.fly.dev
    MANAGER_CHAT_ID = os.getenv("MANAGER_CHAT_ID", "").strip()  # numeric string

    # Locale
    DEFAULT_LANG = os.getenv("DEFAULT_LANG", "ru").strip().lower()  # ru|en

    # Branding / links
    BRAND_NAME = os.getenv("BRAND_NAME", "VEKTOR Web")
    BOT_TG_URL = os.getenv("BOT_TG_URL", "https://t.me/vektorwebbot")

    # Leads API (site -> fly)
    ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").strip()
    LEAD_SECRET = os.getenv("LEAD_SECRET", "").strip()

    # AI (optional)
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()
    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

    @classmethod
    def validate(cls):
        if not cls.BOT_TOKEN:
            raise ValueError("Missing BOT_TOKEN")
        if not cls.DEBUG and not cls.WEBHOOK_URL:
            raise ValueError("Missing WEBHOOK_URL for webhook mode")


config = Config()
