import os


class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    PORT = int(os.getenv("PORT", "8080"))

    MANAGER_CHAT_ID = os.getenv("MANAGER_CHAT_ID")  # numeric string

    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

    LEAD_COOLDOWN_SECONDS = int(os.getenv("LEAD_COOLDOWN_SECONDS", "86400"))
    SUPPORT_TG = os.getenv("SUPPORT_TG", "@bloknotpr")

    @classmethod
    def validate(cls):
        if not cls.BOT_TOKEN:
            raise ValueError("Missing BOT_TOKEN")
        if not cls.DEBUG and not cls.WEBHOOK_URL:
            raise ValueError("Missing WEBHOOK_URL for webhook mode")


config = Config()
