# FILE: src/handlers.py
# Language selector (RU/EN) at dialog start + full i18n for bot UI/messages.
# python-telegram-bot v20+

from __future__ import annotations

import html
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

log = logging.getLogger(__name__)

# ==========
# CONFIG
# ==========
BOT_TG_URL = os.getenv("BOT_TG_URL", "https://t.me/vektorwebbot")
MANAGER_CHAT_ID = os.getenv("MANAGER_CHAT_ID", "").strip()  # numeric chat id recommended
BRAND_NAME = os.getenv("BRAND_NAME", "VEKTOR Web")

AI_ENABLED = os.getenv("AI_ENABLED", "1").strip() not in ("0", "false", "False", "")
MAX_USER_TEXT = 4000
MAX_AI_REPLY = 3500

LANG_RU = "ru"
LANG_EN = "en"
DEFAULT_LANG = os.getenv("DEFAULT_LANG", LANG_RU).strip().lower()
if DEFAULT_LANG not in (LANG_RU, LANG_EN):
    DEFAULT_LANG = LANG_RU


# ==========
# DATA
# ==========
@dataclass(frozen=True)
class Package:
    code: str
    title: Dict[str, str]   # {ru: ..., en: ...}
    price: str
    bullets: Dict[str, Tuple[str, ...]]  # {ru: (...), en: (...)}


PACKAGES: Tuple[Package, ...] = (
    Package(
        "mini",
        {LANG_RU: "Мини-сайт", LANG_EN: "Mini site"},
        "10 000 ₽",
        {
            LANG_RU: ("Лендинг из 1 экрана", "1 форма", "Адаптивность", "Срок: 2 дня"),
            LANG_EN: ("1-screen landing", "1 form", "Responsive", "ETA: 2 days"),
        },
    ),
    Package(
        "blogger",
        {LANG_RU: "Блогер Старт", LANG_EN: "Creator Start"},
        "25 000 ₽",
        {
            LANG_RU: ("Сайт-визитка (4 блока)", "Соцсети", "Простая CMS", "Срок: 4 дня"),
            LANG_EN: ("One-page profile (4 blocks)", "Social links", "Simple CMS", "ETA: 4 days"),
        },
    ),
    Package(
        "profi",
        {LANG_RU: "Профи", LANG_EN: "Pro"},
        "50 000 ₽",
        {
            LANG_RU: ("До 6 экранов", "Cal.com", "Бот уведомлений", "Срок: 5–7 дней"),
            LANG_EN: ("Up to 6 sections", "Cal.com", "Notification bot", "ETA: 5–7 days"),
        },
    ),
    Package(
        "biz",
        {LANG_RU: "Бизнес-Лендинг", LANG_EN: "Business Landing"},
        "75 000 ₽",
        {
            LANG_RU: ("Прототипирование", "A/B структура", "Анимации", "Срок: 7–10 дней"),
            LANG_EN: ("Wireframing", "A/B structure", "Animations", "ETA: 7–10 days"),
        },
    ),
    Package(
        "shop",
        {LANG_RU: "Магазин", LANG_EN: "Shop"},
        "100 000 ₽",
        {
            LANG_RU: ("Каталог до 30", "Фильтры", "Оплата", "Срок: 10–14 дней"),
            LANG_EN: ("Catalog up to 30 items", "Filters", "Payments", "ETA: 10–14 days"),
        },
    ),
    Package(
        "auto",
        {LANG_RU: "Автоматизация", LANG_EN: "Automation"},
        "125 000 ₽",
        {
            LANG_RU: ("Сайт + бот", "Корзина/оплата в боте", "Триггеры", "Срок: 14–18 дней"),
            LANG_EN: ("Site + bot", "Cart/payment in bot", "Triggers", "ETA: 14–18 days"),
        },
    ),
    Package(
        "portfolio",
        {LANG_RU: "Портфолио Pro", LANG_EN: "Portfolio Pro"},
        "150 000 ₽",
        {
            LANG_RU: ("Уникальный дизайн", "Фильтры портфолио", "SEO Pro", "Срок: 18–25 дней"),
            LANG_EN: ("Unique design", "Portfolio filters", "SEO Pro", "ETA: 18–25 days"),
        },
    ),
    Package(
        "custom",
        {LANG_RU: "Индивидуальное решение", LANG_EN: "Custom Solution"},
        "от 200 000 ₽",
        {
            LANG_RU: ("Разработка с нуля", "Интеграции", "Нестандартный функционал", "Срок: от 30 дней"),
            LANG_EN: ("From scratch", "Integrations", "Custom functionality", "ETA: 30+ days"),
        },
    ),
)

# ==========
# i18n STRINGS
# ==========
T: Dict[str, Dict[str, str]] = {
    "lang_choose_title": {
        LANG_RU: "Выберите язык / Choose a language",
        LANG_EN: "Choose a language / Выберите язык",
    },
    "btn_lang_ru": {LANG_RU: "🇷🇺 Русский", LANG_EN: "🇷🇺 Russian"},
    "btn_lang_en": {LANG_RU: "🇬🇧 English", LANG_EN: "🇬🇧 English"},
    "welcome_greeting": {
        LANG_RU: f"Привет! 👋\nЯ бот {BRAND_NAME}.\n",
        LANG_EN: f"Hi! 👋\nI'm the {BRAND_NAME} bot.\n",
    },
    "welcome_about": {
        LANG_RU: (
            "Мы делаем:\n"
            "🟣 сайты под ключ (лендинги/многостраничники/портфолио/магазины)\n"
            "🔵 Telegram/WhatsApp-ботов (консультации, заявки, оплаты, автоматизация)\n"
            "⚡ быстро, аккуратно, с фокусом на конверсию и интеграции\n"
        ),
        LANG_EN: (
            "We build:\n"
            "🟣 turnkey websites (landing pages / multi-page / portfolios / shops)\n"
            "🔵 Telegram/WhatsApp bots (consultation, leads, payments, automation)\n"
            "⚡ fast, clean, conversion-focused, integrations-ready\n"
        ),
    },
    "welcome_manager_line": {
        LANG_RU: "Если вы хотите сделать заказ — обратитесь к Менеджеру. 👤",
        LANG_EN: "If you want to place an order — contact the Manager. 👤",
    },
    "menu_packages": {LANG_RU: "📦 Пакеты и цены", LANG_EN: "📦 Packages & pricing"},
    "menu_services": {LANG_RU: "🧩 Услуги", LANG_EN: "🧩 Services"},
    "menu_order": {LANG_RU: "📝 Оставить заявку", LANG_EN: "📝 Leave a request"},
    "menu_manager": {LANG_RU: "👤 Менеджер", LANG_EN: "👤 Manager"},
    "back": {LANG_RU: "⬅️ Назад", LANG_EN: "⬅️ Back"},
    "packages_title": {LANG_RU: "<b>Пакеты и цены</b> 📦", LANG_EN: "<b>Packages & pricing</b> 📦"},
    "services_title": {LANG_RU: "<b>Услуги</b> 🧩", LANG_EN: "<b>Services</b> 🧩"},
    "services_body": {
        LANG_RU: (
            "🟣 Сайты: лендинги, многостраничники, портфолио, магазины\n"
            "🔵 Боты: Telegram/WhatsApp, заявки, консультации, интеграции, оплаты\n"
            "⚙️ Автоматизация: связка сайт + бот + CRM/таблицы/уведомления"
        ),
        LANG_EN: (
            "🟣 Websites: landing pages, multi-page, portfolio, shops\n"
            "🔵 Bots: Telegram/WhatsApp, leads, consult, integrations, payments\n"
            "⚙️ Automation: site + bot + CRM/sheets/notifications"
        ),
    },
    "order_title": {LANG_RU: "<b>Заявка</b> 📝", LANG_EN: "<b>Request</b> 📝"},
    "order_body": {
        LANG_RU: (
            "Отправьте одним сообщением:\n"
            "1) Имя\n"
            "2) Контакт (Telegram/телефон/email)\n"
            "3) Пакет (или “не знаю”)\n"
            "4) Кратко задачу + сроки\n\n"
            "Я передам менеджеру и он свяжется с вами."
        ),
        LANG_EN: (
            "Send in one message:\n"
            "1) Name\n"
            "2) Contact (Telegram/phone/email)\n"
            "3) Package (or “not sure”)\n"
            "4) Short description + timeline\n\n"
            "I will forward it to the manager."
        ),
    },
    "received_ok": {LANG_RU: "Принято ✅\nМенеджер свяжется с вами.", LANG_EN: "Received ✅\nThe manager will contact you."},
    "pkg_not_found": {LANG_RU: "Пакет не найден.", LANG_EN: "Package not found."},
    "pkg_cta": {
        LANG_RU: "Чтобы оформить заказ, отправьте данные одним сообщением (имя, контакт, задача, сроки).",
        LANG_EN: "To order, send details in one message (name, contact, task, timeline).",
    },
    "prices_title": {LANG_RU: "<b>Прайс по пакетам:</b> 💰", LANG_EN: "<b>Packages pricing:</b> 💰"},
    "lead_title": {LANG_RU: "<b>Новая заявка</b> 🧾", LANG_EN: "<b>New lead</b> 🧾"},
    "lead_user": {LANG_RU: "<b>Пользователь:</b>", LANG_EN: "<b>User:</b>"},
    "lead_pkg": {LANG_RU: "<b>Пакет:</b>", LANG_EN: "<b>Package:</b>"},
    "lead_msg": {LANG_RU: "<b>Сообщение:</b>", LANG_EN: "<b>Message:</b>"},
    "ai_fallback": {
        LANG_RU: "Принял. Уточните нишу, цель и срок — предложу оптимальный пакет и следующий шаг.",
        LANG_EN: "Got it. Share niche, goal, and deadline — I’ll recommend the best package and next steps.",
    },
}


# ==========
# HELPERS
# ==========
def _t(lang: str, key: str) -> str:
    lang = (lang or DEFAULT_LANG).lower()
    if lang not in (LANG_RU, LANG_EN):
        lang = DEFAULT_LANG
    return T.get(key, {}).get(lang) or T.get(key, {}).get(DEFAULT_LANG) or key


def _sanitize_text(text: str) -> str:
    text = text.replace("\x00", "").strip()
    text = re.sub(r"[\x01-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    if len(text) > MAX_USER_TEXT:
        text = text[:MAX_USER_TEXT]
    return text


def _get_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    lang = (context.user_data.get("lang") or "").lower()
    if lang in (LANG_RU, LANG_EN):
        return lang
    return DEFAULT_LANG


def _compact_user(update: Update) -> str:
    u = update.effective_user
    if not u:
        return "unknown-user"
    uname = f"@{u.username}" if u.username else ""
    full = " ".join([x for x in [u.first_name, u.last_name] if x]).strip()
    bits = [str(u.id)]
    if full:
        bits.append(full)
    if uname:
        bits.append(uname)
    return " | ".join(bits)


# ==========
# KEYBOARDS
# ==========
def _keyboard_lang() -> InlineKeyboardMarkup:
    # labels shown in user's current lang (or default)
    lang = DEFAULT_LANG
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(_t(lang, "btn_lang_ru"), callback_data="lang:ru"),
                InlineKeyboardButton(_t(lang, "btn_lang_en"), callback_data="lang:en"),
            ]
        ]
    )


def _keyboard_main(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(_t(lang, "menu_packages"), callback_data="menu:packages"),
                InlineKeyboardButton(_t(lang, "menu_services"), callback_data="menu:services"),
            ],
            [
                InlineKeyboardButton(_t(lang, "menu_order"), callback_data="menu:order"),
                InlineKeyboardButton(_t(lang, "menu_manager"), url=BOT_TG_URL),
            ],
        ]
    )


def _keyboard_packages(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"{p.title[lang]} — {p.price}", callback_data=f"pkg:{p.code}")]
        for p in PACKAGES
    ]
    rows.append([InlineKeyboardButton(_t(lang, "back"), callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def _keyboard_back_home(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(_t(lang, "back"), callback_data="menu:home")]])


def _keyboard_order(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(_t(lang, "menu_manager"), url=BOT_TG_URL)],
            [InlineKeyboardButton(_t(lang, "back"), callback_data="menu:home")],
        ]
    )


# ==========
# TEXT BUILDERS (HTML parse mode; line breaks are '\n')
# ==========
def _fmt_packages_block_html(lang: str) -> str:
    lines = [_t(lang, "prices_title"), ""]
    for p in PACKAGES:
        lines.append(f"• <b>{html.escape(p.title[lang])}</b> — <b>{html.escape(p.price)}</b>")
    return "\n".join(lines)


def _welcome_message_html(lang: str) -> str:
    return (
        f"{html.escape(_t(lang, 'welcome_greeting'))}\n"
        f"{html.escape(_t(lang, 'welcome_about'))}\n"
        f"{_fmt_packages_block_html(lang)}\n\n"
        f"{html.escape(_t(lang, 'welcome_manager_line'))}"
    )


# ==========
# MANAGER SEND
# ==========
async def _send_to_manager(context: ContextTypes.DEFAULT_TYPE, text_html: str) -> None:
    if not MANAGER_CHAT_ID:
        log.warning("MANAGER_CHAT_ID is empty; skipping send to manager.")
        return
    try:
        chat_id = int(MANAGER_CHAT_ID)
    except ValueError:
        log.error("MANAGER_CHAT_ID must be numeric chat id. Current: %r", MANAGER_CHAT_ID)
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text=text_html,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


# ==========
# AI (optional stub)
# ==========
async def call_ai(user_text: str, lang: str) -> str:
    # Replace with your OpenRouter logic; keep lang-aware prompt if you use LLM.
    return _t(lang, "ai_fallback")


# ==========
# COMMANDS
# ==========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    context.user_data.clear()
    context.user_data["state"] = "lang_select"
    context.user_data["started_at"] = datetime.now(timezone.utc).isoformat()

    await update.message.reply_text(
        _t(DEFAULT_LANG, "lang_choose_title"),
        reply_markup=_keyboard_lang(),
        disable_web_page_preview=True,
    )


async def cmd_packages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    lang = _get_lang(context)
    context.user_data["state"] = "packages"
    await update.message.reply_text(
        _t(lang, "packages_title"),
        parse_mode=ParseMode.HTML,
        reply_markup=_keyboard_packages(lang),
    )


# ==========
# CALLBACKS
# ==========
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q:
        return

    data = q.data or ""
    await q.answer()

    # language pick
    if data.startswith("lang:"):
        lang = data.split(":", 1)[1].strip().lower()
        if lang not in (LANG_RU, LANG_EN):
            lang = DEFAULT_LANG
        context.user_data["lang"] = lang
        context.user_data["state"] = "home"

        await q.edit_message_text(
            _welcome_message_html(lang),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=_keyboard_main(lang),
        )
        return

    lang = _get_lang(context)

    if data == "menu:home":
        context.user_data["state"] = "home"
        await q.edit_message_text(
            _welcome_message_html(lang),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=_keyboard_main(lang),
        )
        return

    if data == "menu:packages":
        context.user_data["state"] = "packages"
        await q.edit_message_text(
            _t(lang, "packages_title"),
            parse_mode=ParseMode.HTML,
            reply_markup=_keyboard_packages(lang),
        )
        return

    if data.startswith("pkg:"):
        code = data.split(":", 1)[1]
        pkg = next((p for p in PACKAGES if p.code == code), None)
        if not pkg:
            await q.edit_message_text(_t(lang, "pkg_not_found"), reply_markup=_keyboard_packages(lang))
            return

        context.user_data["selected_package"] = pkg.title[lang]
        context.user_data["state"] = "order"

        bullets = "\n".join([f"• {html.escape(b)}" for b in pkg.bullets[lang]])
        msg = (
            f"<b>{html.escape(pkg.title[lang])}</b> — <b>{html.escape(pkg.price)}</b> ✅\n\n"
            f"{bullets}\n\n"
            f"{html.escape(_t(lang, 'pkg_cta'))}"
        )
        await q.edit_message_text(
            msg,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=_keyboard_order(lang),
        )
        return

    if data == "menu:services":
        context.user_data["state"] = "services"
        await q.edit_message_text(
            f"{_t(lang, 'services_title')}\n\n{html.escape(_t(lang, 'services_body'))}",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=_keyboard_back_home(lang),
        )
        return

    if data == "menu:order":
        context.user_data["state"] = "order"
        await q.edit_message_text(
            f"{_t(lang, 'order_title')}\n\n{html.escape(_t(lang, 'order_body'))}",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=_keyboard_order(lang),
        )
        return


# ==========
# TEXT HANDLER
# ==========
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or update.message.text is None:
        return

    user_text = _sanitize_text(update.message.text)
    if not user_text:
        return

    state = (context.user_data.get("state") or "home").strip()
    lang = _get_lang(context)

    # If user hasn't chosen language yet, keep forcing language selection
    if state == "lang_select" and lang not in (LANG_RU, LANG_EN):
        await update.message.reply_text(_t(DEFAULT_LANG, "lang_choose_title"), reply_markup=_keyboard_lang())
        return

    selected_pkg = (context.user_data.get("selected_package") or "").strip()

    if state == "order":
        lead = {
            "user": _compact_user(update),
            "lang": lang,
            "selected_package": selected_pkg or "—",
            "text": user_text,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

        manager_msg = (
            f"{_t(lang, 'lead_title')}\n"
            f"{_t(lang, 'lead_user')} {html.escape(lead['user'])}\n"
            f"{_t(lang, 'lead_pkg')} {html.escape(lead['selected_package'])}\n"
            f"{_t(lang, 'lead_msg')}\n{html.escape(lead['text'])}\n\n"
            f"<i>raw:</i> {html.escape(json.dumps(lead, ensure_ascii=False))}"
        )
        await _send_to_manager(context, manager_msg)

        await update.message.reply_text(
            _t(lang, "received_ok"),
            reply_markup=_keyboard_main(lang),
        )
        context.user_data["state"] = "home"
        return

    ai_text = await call_ai(user_text, lang) if AI_ENABLED else _t(lang, "ai_fallback")
    ai_text = _sanitize_text(ai_text)
    if len(ai_text) > MAX_AI_REPLY:
        ai_text = ai_text[:MAX_AI_REPLY]

    await update.message.reply_text(ai_text, disable_web_page_preview=True, reply_markup=_keyboard_main(lang))


# ==========
# OPTIONAL: CONTACT ACCEPTOR
# ==========
async def accept_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.contact:
        return

    lang = _get_lang(context)
    c = update.message.contact
    phone = (c.phone_number or "").strip()
    first = (c.first_name or "").strip()
    last = (c.last_name or "").strip()

    msg = (
        "<b>Contact received</b> 📇\n"
        f"<b>User:</b> {html.escape(_compact_user(update))}\n"
        f"<b>Name:</b> {html.escape(' '.join([first, last]).strip() or '—')}\n"
        f"<b>Phone:</b> {html.escape(phone or '—')}"
    )
    await _send_to_manager(context, msg)

    await update.message.reply_text(
        "OK ✅" if lang == LANG_EN else "Принято ✅",
        reply_markup=_keyboard_main(lang),
    )
