# FILE: src/handlers.py
# python-telegram-bot v20+
from __future__ import annotations

import html
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

log = logging.getLogger(__name__)

# ==========
# CONFIG
# ==========
BOT_TG_URL = os.getenv("BOT_TG_URL", "https://t.me/vektorwebbot")
MANAGER_CHAT_ID = os.getenv("MANAGER_CHAT_ID", "").strip()  # numeric chat id recommended
BRAND_NAME = os.getenv("BRAND_NAME", "VEKTOR Web")

# If you use OpenRouter in your project, keep it in your own module.
# This handlers.py is safe without OpenRouter. If you already have ai_client.py,
# you can plug it into call_ai() below.
AI_ENABLED = os.getenv("AI_ENABLED", "1").strip() not in ("0", "false", "False", "")
AI_MODEL = os.getenv("AI_MODEL", "").strip()

# Limits to prevent sending garbage / too long
MAX_USER_TEXT = 4000
MAX_AI_REPLY = 3500


# ==========
# DATA
# ==========
@dataclass(frozen=True)
class Package:
    code: str
    title: str
    price: str
    bullets: Tuple[str, ...]


PACKAGES: Tuple[Package, ...] = (
    Package(
        code="mini",
        title="Мини-сайт",
        price="10 000 ₽",
        bullets=("Лендинг из 1 экрана", "1 форма", "Адаптивность", "Срок: 2 дня"),
    ),
    Package(
        code="blogger",
        title="Блогер Старт",
        price="25 000 ₽",
        bullets=("Сайт-визитка (4 блока)", "Соцсети", "Простая CMS", "Срок: 4 дня"),
    ),
    Package(
        code="profi",
        title="Профи",
        price="50 000 ₽",
        bullets=("До 6 экранов", "Cal.com", "Бот уведомлений", "Срок: 5–7 дней"),
    ),
    Package(
        code="biz",
        title="Бизнес-Лендинг",
        price="75 000 ₽",
        bullets=("Прототипирование", "A/B структура", "Анимации", "Срок: 7–10 дней"),
    ),
    Package(
        code="shop",
        title="Магазин",
        price="100 000 ₽",
        bullets=("Каталог до 30", "Фильтры", "Оплата", "Срок: 10–14 дней"),
    ),
    Package(
        code="auto",
        title="Автоматизация",
        price="125 000 ₽",
        bullets=("Сайт + бот", "Корзина/оплата в боте", "Триггеры", "Срок: 14–18 дней"),
    ),
    Package(
        code="portfolio",
        title="Портфолио Pro",
        price="150 000 ₽",
        bullets=("Уникальный дизайн", "Фильтры портфолио", "SEO Pro", "Срок: 18–25 дней"),
    ),
    Package(
        code="custom",
        title="Индивидуальное решение",
        price="от 200 000 ₽",
        bullets=("Разработка с нуля", "Интеграции", "Нестандартный функционал", "Срок: от 30 дней"),
    ),
)

WELCOME_GREETING = (
    "Привет! 👋\n"
    f"Я бот {BRAND_NAME}.\n"
)

WELCOME_ABOUT = (
    "Мы делаем:\n"
    "🟣 сайты под ключ (лендинги/многостраничники/портфолио/магазины)\n"
    "🔵 Telegram/WhatsApp-ботов (консультации, заявки, оплаты, автоматизация)\n"
    "⚡ быстро, аккуратно, с фокусом на конверсию и интеграции\n"
)

WELCOME_MANAGER_LINE = (
    "Если вы хотите сделать заказ — обратитесь к Менеджеру. 👤"
)

# ==========
# UI
# ==========
def _keyboard_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📦 Пакеты и цены", callback_data="menu:packages"),
                InlineKeyboardButton("🧩 Услуги", callback_data="menu:services"),
            ],
            [
                InlineKeyboardButton("📝 Оставить заявку", callback_data="menu:order"),
                InlineKeyboardButton("👤 Менеджер", url=BOT_TG_URL),
            ],
        ]
    )


def _keyboard_packages() -> InlineKeyboardMarkup:
    rows = []
    for p in PACKAGES:
        rows.append([InlineKeyboardButton(f"{p.title} — {p.price}", callback_data=f"pkg:{p.code}")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def _keyboard_order() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("👤 Написать менеджеру", url=BOT_TG_URL)],
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu:home")],
        ]
    )


# ==========
# TEXT BUILDERS (HTML-safe)
# ==========
def _fmt_packages_block() -> str:
    lines = ["<b>Прайс по пакетам:</b> 💰", ""]
    for p in PACKAGES:
        lines.append(f"• <b>{html.escape(p.title)}</b> — <b>{html.escape(p.price)}</b>")
    return "\n".join(lines)


def _welcome_message() -> str:
    parts = [
        html.escape(WELCOME_GREETING).replace("\n", "<br>"),
        "<br>",
        html.escape(WELCOME_ABOUT).replace("\n", "<br>"),
        "<br>",
        _fmt_packages_block().replace("\n", "<br>"),
        "<br><br>",
        html.escape(WELCOME_MANAGER_LINE),
    ]
    return "".join(parts)


def _services_message() -> str:
    return (
        "<b>Услуги</b> 🧩<br><br>"
        "🟣 Сайты: лендинги, многостраничники, портфолио, магазины<br>"
        "🔵 Боты: Telegram/WhatsApp, заявки, консультации, интеграции, оплаты<br>"
        "⚙️ Автоматизация: связка сайт + бот + CRM/таблицы/уведомления"
    )


def _order_hint() -> str:
    return (
        "<b>Заявка</b> 📝<br><br>"
        "Отправьте одним сообщением:<br>"
        "1) Имя<br>"
        "2) Контакт (Telegram/телефон/email)<br>"
        "3) Пакет (или “не знаю”)<br>"
        "4) Кратко задачу + сроки<br><br>"
        "Я передам менеджеру и он свяжется с вами."
    )


# ==========
# MANAGER SEND
# ==========
async def _send_to_manager(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
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
        text=text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


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
# AI (optional)
# ==========
async def call_ai(user_text: str) -> str:
    """
    Plug your OpenRouter client here if you already have one.
    This stub avoids crashes and returns a safe fallback.
    """
    # If you have an existing module: from .openrouter_client import ask
    # return await ask(user_text=user_text)

    # Safe fallback (no symbols, no binary)
    return (
        "Принял. Уточните, пожалуйста, нишу, цель сайта/бота и желаемый срок — "
        "и я предложу оптимальный пакет и следующий шаг."
    )


# ==========
# COMMANDS
# ==========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /start
    Sends a structured welcome message + packages + manager line (with emojis).
    """
    if not update.message:
        return

    # Clear state on new start
    context.user_data.clear()
    context.user_data["state"] = "home"
    context.user_data["started_at"] = datetime.now(timezone.utc).isoformat()

    await update.message.reply_text(
        _welcome_message(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=_keyboard_main(),
    )


async def cmd_packages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    context.user_data["state"] = "packages"
    await update.message.reply_text(
        "<b>Пакеты и цены</b> 📦",
        parse_mode=ParseMode.HTML,
        reply_markup=_keyboard_packages(),
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

    if data == "menu:home":
        context.user_data["state"] = "home"
        await q.edit_message_text(
            _welcome_message(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=_keyboard_main(),
        )
        return

    if data == "menu:packages":
        context.user_data["state"] = "packages"
        await q.edit_message_text(
            "<b>Пакеты и цены</b> 📦",
            parse_mode=ParseMode.HTML,
            reply_markup=_keyboard_packages(),
        )
        return

    if data.startswith("pkg:"):
        code = data.split(":", 1)[1]
        pkg = next((p for p in PACKAGES if p.code == code), None)
        if not pkg:
            await q.edit_message_text(
                "Пакет не найден.",
                reply_markup=_keyboard_packages(),
            )
            return

        context.user_data["selected_package"] = pkg.title
        context.user_data["state"] = "order"

        bullets = "<br>".join([f"• {html.escape(b)}" for b in pkg.bullets])
        msg = (
            f"<b>{html.escape(pkg.title)}</b> — <b>{html.escape(pkg.price)}</b> ✅<br><br>"
            f"{bullets}<br><br>"
            "Чтобы оформить заказ, отправьте данные одним сообщением (имя, контакт, задача, сроки)."
        )
        await q.edit_message_text(
            msg,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=_keyboard_order(),
        )
        return

    if data == "menu:services":
        context.user_data["state"] = "services"
        await q.edit_message_text(
            _services_message(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="menu:home")]]),
        )
        return

    if data == "menu:order":
        context.user_data["state"] = "order"
        await q.edit_message_text(
            _order_hint(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=_keyboard_order(),
        )
        return


# ==========
# TEXT HANDLER
# ==========
def _sanitize_text(text: str) -> str:
    text = text.replace("\x00", "").strip()
    # remove control chars except newline/tab
    text = re.sub(r"[\x01-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    if len(text) > MAX_USER_TEXT:
        text = text[:MAX_USER_TEXT]
    return text


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Main text router.
    - In "order" state: treat incoming message as lead and forward to manager.
    - Otherwise: optional AI response (safe fallback if AI not wired).
    """
    if not update.message or update.message.text is None:
        return

    user_text = _sanitize_text(update.message.text)
    if not user_text:
        return

    state = (context.user_data.get("state") or "home").strip()
    selected_pkg = (context.user_data.get("selected_package") or "").strip()

    if state == "order":
        lead = {
            "user": _compact_user(update),
            "selected_package": selected_pkg or "—",
            "text": user_text,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

        manager_msg = (
            "<b>Новая заявка</b> 🧾<br>"
            f"<b>Пользователь:</b> {html.escape(lead['user'])}<br>"
            f"<b>Пакет:</b> {html.escape(lead['selected_package'])}<br>"
            f"<b>Сообщение:</b><br>{html.escape(lead['text']).replace(chr(10), '<br>')}<br><br>"
            f"<i>raw:</i> {html.escape(json.dumps(lead, ensure_ascii=False))}"
        )
        await _send_to_manager(context, manager_msg)

        await update.message.reply_text(
            "Принято ✅\nМенеджер свяжется с вами.",
            reply_markup=_keyboard_main(),
        )
        context.user_data["state"] = "home"
        return

    # Non-order: consult mode
    if AI_ENABLED:
        ai_text = await call_ai(user_text)
    else:
        ai_text = "Принято."

    ai_text = _sanitize_text(ai_text)
    if len(ai_text) > MAX_AI_REPLY:
        ai_text = ai_text[:MAX_AI_REPLY]

    await update.message.reply_text(ai_text, disable_web_page_preview=True)


# ==========
# OPTIONAL: CONTACT ACCEPTOR (fixed)
# ==========
async def accept_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    If you later add a contact request button, this handler will accept it safely.
    Fixes the SyntaxError you had: no broken parentheses, no partial identifiers.
    """
    if not update.message or not update.message.contact:
        return

    c = update.message.contact
    phone = (c.phone_number or "").strip()
    first = (c.first_name or "").strip()
    last = (c.last_name or "").strip()

    msg = (
        "<b>Контакт получен</b> 📇<br>"
        f"<b>Пользователь:</b> {html.escape(_compact_user(update))}<br>"
        f"<b>Имя:</b> {html.escape(' '.join([first, last]).strip() or '—')}<br>"
        f"<b>Телефон:</b> {html.escape(phone or '—')}"
    )
    await _send_to_manager(context, msg)

    await update.message.reply_text("Контакт принят ✅", reply_markup=_keyboard_main())
