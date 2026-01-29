# ==========
# CONFIG
# ==========
from .config import config

BOT_TG_URL = config.BOT_TG_URL
MANAGER_CHAT_ID = config.MANAGER_CHAT_ID
BRAND_NAME = config.BRAND_NAME

AI_ENABLED = (os.getenv("AI_ENABLED", "1").strip() not in ("0", "false", "False", ""))
MAX_USER_TEXT = 4000
MAX_AI_REPLY = 3500

LANG_RU = "ru"
LANG_EN = "en"
DEFAULT_LANG = os.getenv("DEFAULT_LANG", LANG_RU).strip().lower()
if DEFAULT_LANG not in (LANG_RU, LANG_EN):
    DEFAULT_LANG = LANG_RU
