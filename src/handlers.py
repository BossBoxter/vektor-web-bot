# FILE: src/handlers.py
from __future__ import annotations

import html
import os
from dataclasses import dataclass
from typing import Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes


# =========================
# CONFIG
# =========================
BOT_USERNAME = os.getenv("BOT_USERNAME", "vektorwebbot")
MANAGER_CHAT_ID = os.getenv("MANAGER_CHAT_ID")  # обязательно в Secrets/Env
MANAGER_THREAD_ID = os.getenv("MANAGER_THREAD_ID")  # опционально (для topics)
SITE_NAME = os.getenv("SITE_NAME", "Vektor Web")

# Packages (единый источник истины)
PACKAGES = [
    ("Мини-сайт", "10 000 ₽"),
    ("Блогер Старт", "25 000 ₽"),
    ("Профи", "50 000 ₽"),
    ("Бизнес-Лендинг", "75 000 ₽"),
    ("Магазин", "100 000 ₽"),
    ("Автоматизация", "125 000 ₽"),
    ("Портфолио Pro", "150 000 ₽"),
    ("Индивидуальное решение", "от 200 000 ₽"),
]

# States
S_MENU = "MENU"
S_LEAD_NAME = "LEAD_NAME"
S_LEAD_CONTACT = "LEAD_CONTACT"
S_LEAD_PACKAGE = "LEAD_PACKAGE"
S_LEAD_DESC = "LEAD_DESC"
S_LEAD_CONFIRM = "LEAD_CONFIRM"

UD_STATE = "state"
UD_LEAD = "lead"


@dataclass
class Lead:
    name: str = ""
    contact: str = ""
    package: str = ""
    description: str = ""
    source: str = ""  # /start payload or other


def _ud_get_lead(user_data: dict) -> Lead:
    raw = user_data.get(UD_LEAD)
    if isinstance(raw, Lead):
        return raw
    lead = Lead()
    user_data[UD_LEAD] = lead
    return lead


def _ud_set_state(user_data: dict, state: str) -> None:
    user_data[UD_STATE] = state


def _ud_get_state(user_data: dict) -> str:
    return user_data.get(UD_STATE, S_MENU)


def _safe(s: Optional[str]) -> str:
    return html.escape((s or "").strip())


def _parse_start_payload(text: str) -> str:
    # text: "/start xxx"
    parts = (text or "").split(maxsplit=1)
    if len(parts) < 2:
        return ""
    payload = parts[1].strip()
    # payload length is limited by Telegram; keep as-is
    return payload


# =========================
# INLINE KEYBOARDS
# =========================
def kb_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Пакеты", callback_data="NAV:PACKAGES"),
                InlineKeyboardButton("Оставить заявку", callback_data="LEAD:START"),
            ],
            [
                InlineKeyboardButton("Как мы работаем", callback_data="NAV:PROCESS"),
                InlineKeyboardButton("Контакты", callback_data="NAV:CONTACTS"),
            ],
        ]
    )


def kb_back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Назад в меню", callback_data="NAV:MENU")]])


def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Отмена", callback_data="LEAD:CANCEL")]])


def kb_packages() -> InlineKeyboardMarkup:
    rows = []
    for name, price in PACKAGES:
        rows.append([InlineKeyboardButton(f"{name} — {price}", callback_data=f"LEAD:PKG:{name}")])
    rows.append([InlineKeyboardButton("Назад", callback_data="NAV:MENU")])
    return InlineKeyboardMarkup(rows)


def kb_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Отправить", callback_data="LEAD:SEND"),
                InlineKeyboardButton("Отмена", callback_data="LEAD:CANCEL"),
            ],
            [InlineKeyboardButton("В меню", callback_data="NAV:MENU")],
        ]
    )


# =========================
# RENDER
# =========================
def render_menu_text() -> str:
    return (
        "<b>VEKTOR Web</b>\n"
        "Сайты и Telegram-боты под ключ.\n\n"
        "Выберите действие:"
    )


def render_packages_text() -> str:
    lines = ["<b>Пакеты</b>\n"]
    for name, price in PACKAGES:
        lines.append(f"• <b>{_safe(name)}</b> — {_safe(price)}")
    lines.append("\nНажмите на пакет, чтобы сразу оформить заявку.")
    return "\n".join(lines)


def render_process_text() -> str:
    return (
        "<b>Процесс</b>\n"
        "1) Заявка\n"
        "2) Разбор 20 минут\n"
        "3) Аванс 50% + договор\n"
        "4) Прототип\n"
        "5) Разработка\n"
        "6) Тестирование\n"
        "7) Запуск\n"
    )


def render_contacts_text() -> str:
    return (
        "<b>Контакты</b>\n"
        f"Бот: @{_safe(BOT_USERNAME)}\n"
        "Email: vectorweb9881@gmail.com\n"
        "Instagram: @vektor_web"
    )


def render_lead_summary(lead: Lead, user_link: str) -> str:
    return (
        "<b>Проверьте заявку</b>\n\n"
        f"Имя: <b>{_safe(lead.name) or '-'}</b>\n"
        f"Контакт: <b>{_safe(lead.contact) or '-'}</b>\n"
        f"Пакет: <b>{_safe(lead.package) or '-'}</b>\n"
        f"Описание:\n{_safe(lead.description) or '-'}\n\n"
        f"Пользователь: {user_link}\n"
        f"Источник: <code>{_safe(lead.source) or '-'}</code>"
    )


def user_tg_link(update: Update) -> str:
    u = update.effective_user
    if not u:
        return "<i>unknown</i>"
    name = _safe(u.full_name) or "user"
    return f"<a href='tg://user?id={u.id}'>{name}</a>"


# =========================
# MANAGER NOTIFY
# =========================
async def notify_manager(update: Update, context: ContextTypes.DEFAULT_TYPE, lead: Lead) -> None:
    if not MANAGER_CHAT_ID:
        return

    u = update.effective_user
    uname = f"@{u.username}" if (u and u.username) else ""
    link = user_tg_link(update)

    text = (
        "<b>Новая заявка</b>\n\n"
        f"Имя: <b>{_safe(lead.name) or '-'}</b>\n"
        f"Контакт: <b>{_safe(lead.contact) or '-'}</b>\n"
        f"Пакет: <b>{_safe(lead.package) or '-'}</b>\n"
        f"Описание:\n{_safe(lead.description) or '-'}\n\n"
        f"Пользователь: {link} {_safe(uname)}\n"
        f"Источник: <code>{_safe(lead.source) or '-'}</code>"
    )

    kwargs = {}
    if MANAGER_THREAD_ID:
        try:
            kwargs["message_thread_id"] = int(MANAGER_THREAD_ID)
        except Exception:
            pass

    await context.bot.send_message(
        chat_id=int(MANAGER_CHAT_ID),
        text=text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        **kwargs,
    )


# =========================
# FLOW CORE
# =========================
def reset_flow(user_data: dict) -> None:
    user_data[UD_LEAD] = Lead()
    _ud_set_state(user_data, S_MENU)


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, *, edit: bool = False) -> None:
    text = render_menu_text()
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(
            text=text, reply_markup=kb_menu(), parse_mode=ParseMode.HTML
        )
        return
    if update.message:
        await update.message.reply_text(text=text, reply_markup=kb_menu(), parse_mode=ParseMode.HTML)


async def start_lead(update: Update, context: ContextTypes.DEFAULT_TYPE, *, preset_package: str = "") -> None:
    lead = _ud_get_lead(context.user_data)
    if preset_package:
        lead.package = preset_package

    _ud_set_state(context.user_data, S_LEAD_NAME)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text="Введите имя:", reply_markup=kb_cancel(), parse_mode=ParseMode.HTML
        )
    elif update.message:
        await update.message.reply_text("Введите имя:", reply_markup=kb_cancel(), parse_mode=ParseMode.HTML)


async def finalize_lead(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lead = _ud_get_lead(context.user_data)

    # 1) Ответ клиенту (одно сообщение, без мусора)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=(
                "Принято.\n"
                "Заявка передана менеджеру.\n"
                "В ближайшее время с вами свяжутся."
            ),
            reply_markup=kb_menu(),
            parse_mode=ParseMode.HTML,
        )
    elif update.message:
        await update.message.reply_text(
            text=(
                "Принято.\n"
                "Заявка передана менеджеру.\n"
                "В ближайшее время с вами свяжутся."
            ),
            reply_markup=kb_menu(),
            parse_mode=ParseMode.HTML,
        )

    # 2) Уведомление менеджеру
    await notify_manager(update, context, lead)

    # 3) Reset
    reset_flow(context.user_data)


# =========================
# PUBLIC HANDLERS
# =========================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reset_flow(context.user_data)

    payload = _parse_start_payload(update.message.text if update.message else "")
    lead = _ud_get_lead(context.user_data)
    lead.source = payload or "start"

    await show_menu(update, context, edit=False)


async def cmd_packages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ud_set_state(context.user_data, S_MENU)
    if update.message:
        await update.message.reply_text(
            text=render_packages_text(),
            reply_markup=kb_packages(),
            parse_mode=ParseMode.HTML,
        )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q:
        return
    await q.answer()

    data = q.data or ""

    # NAV
    if data == "NAV:MENU":
        reset_flow(context.user_data)
        await show_menu(update, context, edit=True)
        return

    if data == "NAV:PACKAGES":
        _ud_set_state(context.user_data, S_MENU)
        await q.edit_message_text(
            text=render_packages_text(),
            reply_markup=kb_packages(),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "NAV:PROCESS":
        _ud_set_state(context.user_data, S_MENU)
        await q.edit_message_text(
            text=render_process_text(),
            reply_markup=kb_back_menu(),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "NAV:CONTACTS":
        _ud_set_state(context.user_data, S_MENU)
        await q.edit_message_text(
            text=render_contacts_text(),
            reply_markup=kb_back_menu(),
            parse_mode=ParseMode.HTML,
        )
        return

    # LEAD
    if data == "LEAD:CANCEL":
        reset_flow(context.user_data)
        await q.edit_message_text(
            text="Отменено. В меню:",
            reply_markup=kb_menu(),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "LEAD:START":
        lead = _ud_get_lead(context.user_data)
        if not lead.source:
            lead.source = "button"
        await start_lead(update, context, preset_package="")
        return

    if data.startswith("LEAD:PKG:"):
        pkg = data.split("LEAD:PKG:", 1)[1].strip()
        lead = _ud_get_lead(context.user_data)
        lead.package = pkg
        if not lead.source:
            lead.source = "packages"
        await start_lead(update, context, preset_package=pkg)
        return

    if data == "LEAD:SEND":
        st = _ud_get_state(context.user_data)
        if st != S_LEAD_CONFIRM:
            # Если кто-то нажал "Отправить" вне подтверждения — просто меню.
            reset_flow(context.user_data)
            await show_menu(update, context, edit=True)
            return
        await finalize_lead(update, context)
        return

    # Default
    reset_flow(context.user_data)
    await show_menu(update, context, edit=True)


def accept_contact(text: str) -> str:
    """
    Нормализация контакта.
    Убирает лишние пробелы, поддерживает @username/телефон/email в одном поле.
    """
    s = (text or "").strip()
    s = " ".join(s.split())
    return s


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg:
        return

    lead = _ud_get_lead(context.user_data)
    state = _ud_get_state(context.user_data)

    # Если пользователь прислал контакт объектом Telegram
    if msg.contact and state in (S_LEAD_CONTACT,):
        phone = msg.contact.phone_number or ""
        text = accept_contact(phone)
    else:
        text = accept_contact(msg.text or "")

    if state == S_LEAD_NAME:
        lead.name = text
        _ud_set_state(context.user_data, S_LEAD_CONTACT)
        await msg.reply_text("Введите контакт (Telegram @username / телефон / email):", reply_markup=kb_cancel())
        return

    if state == S_LEAD_CONTACT:
        lead.contact = text
        _ud_set_state(context.user_data, S_LEAD_PACKAGE)

        # Если пакет уже выбран с сайта/кнопок — пропускаем выбор
        if lead.package:
            _ud_set_state(context.user_data, S_LEAD_DESC)
            await msg.reply_text("Кратко опишите задачу:", reply_markup=kb_cancel())
            return

        await msg.reply_text(
            "Выберите пакет кнопкой ниже:",
            reply_markup=kb_packages(),
            parse_mode=ParseMode.HTML,
        )
        return

    if state == S_LEAD_DESC:
        lead.description = text
        _ud_set_state(context.user_data, S_LEAD_CONFIRM)

        summary = render_lead_summary(lead, user_tg_link(update))
        await msg.reply_text(summary, reply_markup=kb_confirm(), parse_mode=ParseMode.HTML)
        return

    # Любой текст вне формы -> меню (без мусора)
    reset_flow(context.user_data)
    await msg.reply_text(render_menu_text(), reply_markup=kb_menu(), parse_mode=ParseMode.HTML)
