# FILE: src/handlers.py
# FIX: Telegram HTML parse_mode does NOT support <br>. Use '\n' for new lines.
# python-telegram-bot v20+

from __future__ import annotations

import html
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Tuple

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
    Package("mini", "Мини-сайт", "10 000 ₽", ("Лендинг из 1 экрана", "1 форма", "Адаптивность", "Срок: 2 дня")),
    Package("blogger", "Блогер Старт", "25 000 ₽", ("Сайт-визитка (4 блока)", "Соцсети", "Простая CMS", "Срок: 4 дня")),
    Package("profi", "Профи", "50 000 ₽", ("До 6 экранов", "Cal.com", "Бот уведомлений", "Срок: 5–7 дней")),
    Package("biz", "Бизнес-Лендинг", "75 000 ₽", ("Прототипирование", "A/B структура", "Анимации", "Срок: 7–10 дней")),
    Package("shop", "Магазин", "100 000 ₽", ("Каталог до 30", "Фильтры", "Оплата", "Срок: 10–14 дней")),
    Package("auto", "Автоматизация", "125 000 ₽", ("Сайт + бот", "Корзина/оплата в боте", "Триггеры", "Срок: 14–18 дней")),
    Package("portfolio", "Портфолио Pro", "150 000 ₽", ("Уникальный дизайн", "Фильтры портфолио", "SEO Pro", "Срок: 18–25 дней")),
    Package("custom", "Индивидуальное решение", "от 200 000 ₽", ("Разработка с нуля", "Интеграции", "Нестандартный функционал", "Срок: от 30 дней")),
)

WELCOME_GREETING = f"Привет! 👋\nЯ бот {BRAND_NAME}.\n"

WELCOME_ABOUT = (
    "Мы делаем:\n"
    "🟣 сайты под ключ (лендинги/многостраничники/портфолио/магазины)\n"
    "🔵 Telegram/WhatsApp-ботов (консультации, заявки, оплаты, автоматизация)\n"
    "⚡ быстро, аккуратно, с фокусом на конверсию и интеграции\n"
)

WELCOME_MANAGER_LINE = "Если вы хотите сделать заказ — обратитесь к Менеджеру. 👤"


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
    rows = [[InlineKeyboardButton(f"{p.title} — {p.price}", callback_data=f"pkg:{p.code}")] for p in PACKAGES]
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def _keyboard_back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="menu:home")]])


def _keyboard_order() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("👤 Написать менеджеру", url=BOT_TG_URL)],
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu:home")],
        ]
    )


# ==========
# TEXT (HTML mode, BUT NEWLINES ARE '\n', NOT <br>)
# ==========
def _fmt_packages_block_html() -> str:
    lines = ["<b>Прайс по пакетам:</b> 💰", ""]
    for p in PACKAGES:
        lines.append(f"• <b>{html.escape(p.title)}</b> — <b>{html.escape(p.price)}</b>")
    return "\n".join(lines)


def _welcome_message_html() -> str:
    return (
        f"{html.escape(WELCOME_GREETING)}\n"
        f"{html.escape(WELCOME_ABOUT)}\n"
        f"{_fmt_packages_block_html()}\n\n"
        f"{html.escape(WELCOME_MANAGER_LINE)}"
    )


def _services_message_html() -> str:
    return (
        "<b>Услуги</b> 🧩\n\n"
        "🟣 Сайты: лендинги, многостраничники, портфолио, магазины\n"
        "🔵 Боты: Telegram/WhatsApp, заявки, консультации, интеграции, оплаты\n"
        "⚙️ Автоматизация: связка сайт + бот + CRM/таблицы/уведомления"
    )


def _order_hint_html() -> str:
    return (
        "<b>Заявка</b> 📝\n\n"
        "Отправьте одним сообщением:\n"
        "1) Имя\n"
        "2) Контакт (Telegram/телефон/email)\n"
        "3) Пакет (или “не знаю”)\n"
        "4) Кратко задачу + сроки\n\n"
        "Я передам менеджеру и он свяжется с вами."
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
# AI (optional stub)
# ==========
async def call_ai(user_text: str) -> str:
    return (
        "Принял. Уточните нишу, цель и срок — предложу оптимальный пакет и следующий шаг."
    )


# ==========
# HELPERS
# ==========
def _sanitize_text(text: str) -> str:
    text = text.replace("\x00", "").strip()
    text = re.sub(r"[\x01-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    if len(text) > MAX_USER_TEXT:
        text = text[:MAX_USER_TEXT]
    return text


# ==========
# COMMANDS
# ==========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    context.user_data.clear()
    context.user_data["state"] = "home"
    context.user_data["started_at"] = datetime.now(timezone.utc).isoformat()

    await update.message.reply_text(
        _welcome_message_html(),
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
            _welcome_message_html(),
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
            await q.edit_message_text("Пакет не найден.", reply_markup=_keyboard_packages())
            return

        context.user_data["selected_package"] = pkg.title
        context.user_data["state"] = "order"

        bullets = "\n".join([f"• {html.escape(b)}" for b in pkg.bullets])
        msg = (
            f"<b>{html.escape(pkg.title)}</b> — <b>{html.escape(pkg.price)}</b> ✅\n\n"
            f"{bullets}\n\n"
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
            _services_message_html(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=_keyboard_back_home(),
        )
        return

    if data == "menu:order":
        context.user_data["state"] = "order"
        await q.edit_message_text(
            _order_hint_html(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=_keyboard_order(),
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
    selected_pkg = (context.user_data.get("selected_package") or "").strip()

    if state == "order":
        lead = {
            "user": _compact_user(update),
            "selected_package": selected_pkg or "—",
            "text": user_text,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

        manager_msg = (
            "<b>Новая заявка</b> 🧾\n"
            f"<b>Пользователь:</b> {html.escape(lead['user'])}\n"
            f"<b>Пакет:</b> {html.escape(lead['selected_package'])}\n"
            f"<b>Сообщение:</b>\n{html.escape(lead['text'])}\n\n"
            f"<i>raw:</i> {html.escape(json.dumps(lead, ensure_ascii=False))}"
        )
        await _send_to_manager(context, manager_msg)

        await update.message.reply_text(
            "Принято ✅\nМенеджер свяжется с вами.",
            reply_markup=_keyboard_main(),
        )
        context.user_data["state"] = "home"
        return

    ai_text = await call_ai(user_text) if AI_ENABLED else "Принято."
    ai_text = _sanitize_text(ai_text)
    if len(ai_text) > MAX_AI_REPLY:
        ai_text = ai_text[:MAX_AI_REPLY]

    await update.message.reply_text(ai_text, disable_web_page_preview=True)


# ==========
# OPTIONAL: CONTACT ACCEPTOR
# ==========
async def accept_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.contact:
        return

    c = update.message.contact
    phone = (c.phone_number or "").strip()
    first = (c.first_name or "").strip()
    last = (c.last_name or "").strip()

    msg = (
        "<b>Контакт получен</b> 📇\n"
        f"<b>Пользователь:</b> {html.escape(_compact_user(update))}\n"
        f"<b>Имя:</b> {html.escape(' '.join([first, last]).strip() or '—')}\n"
        f"<b>Телефон:</b> {html.escape(phone or '—')}"
    )
    await _send_to_manager(context, msg)

    await update.message.reply_text("Контакт принят ✅", reply_markup=_keyboard_main())
