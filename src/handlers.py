# src/handlers.py
from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Dict, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .config import config
from .text import strings
from .ui import PACKAGES, menu_kb, packages_kb, render_package_text, package_details_kbhow_text, how_kb, lead_cancel_kb
from .openrouter import ask_openrouter



MAX_USER_TEXT = 4000
MAX_AI_REPLY = 3500


@dataclass
class LeadDraft:
    package_name: str
    name: str = ""
    contact: str = ""
    comment: str = ""
    step: str = "name"  # name -> contact -> comment


_leads: Dict[int, LeadDraft] = {}


def _lang() -> str:
    return config.DEFAULT_LANG if config.DEFAULT_LANG in ("ru", "en") else "ru"


def _esc(s: str) -> str:
    return html.escape(s or "", quote=False)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = _lang()
    s = strings(lang)
    title = f"{s.start_title} {config.BRAND_NAME}"
    await update.effective_message.reply_text(f"{title}\n\n{s.start_body}", reply_markup=menu_kb())


async def cmd_packages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(strings(_lang()).choose_package, reply_markup=packages_kb())


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""

    # NAV
    if data == "NAV:MENU":
        await q.message.reply_text("Меню:", reply_markup=menu_kb())
        await q.answer()
        return

    if data == "NAV:PACKAGES":
        await q.message.reply_text(strings(_lang()).choose_package, reply_markup=packages_kb())
        await q.answer()
        return

    # package selection
    if data.startswith("PKG:"):
        name = data.split(":", 1)[1]
        if name not in PACKAGES:
            await q.answer("Не найдено", show_alert=True)
            return
        await q.message.reply_text(render_package_text(name), parse_mode=ParseMode.HTML, reply_markup=package_details_kb())
        context.user_data["selected_package"] = name
        await q.answer()
        return

    # lead flow
    if data == "LEAD:ORDER":
        name = context.user_data.get("selected_package")
        if not name or name not in PACKAGES:
            await q.answer("Сначала выберите пакет", show_alert=True)
            return
        _leads[q.from_user.id] = LeadDraft(package_name=name, step="name")
        await q.message.reply_text(strings(_lang()).ask_name)
        await q.answer()
        return

    if data == "LEAD:CANCEL":
        _leads.pop(q.from_user.id, None)
        await q.message.reply_text("Отменено.", reply_markup=menu_kb())
        await q.answer()
        return

    await q.answer()


async def _notify_manager(update: Update, lead: LeadDraft):
    if not config.MANAGER_CHAT_ID:
        return
    try:
        chat_id = int(config.MANAGER_CHAT_ID)
    except Exception:
        return

    pkg = PACKAGES.get(lead.package_name, {})
    price = pkg.get("price", "")
    time_ = pkg.get("time", "")

    text = (
        "<b>🆕 Новая заявка</b>\n"
        f"<b>Бренд:</b> {_esc(config.BRAND_NAME)}\n"
        f"<b>Пакет:</b> {_esc(lead.package_name)} ({_esc(price)} / {_esc(time_)})\n"
        f"<b>Имя:</b> {_esc(lead.name)}\n"
        f"<b>Контакт:</b> {_esc(lead.contact)}\n"
        f"<b>Комментарий:</b>\n{_esc(lead.comment)}\n\n"
        f"<b>От:</b> @{_esc(update.effective_user.username or '—')} / id={update.effective_user.id}"
    )

    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return

    text = (msg.text or "").strip()
    if not text:
        return
    if len(text) > MAX_USER_TEXT:
        await msg.reply_text(strings(_lang()).too_long)
        return

    uid = update.effective_user.id

    # lead form
    if uid in _leads:
        lead = _leads[uid]

        if lead.step == "name":
            lead.name = text
            lead.step = "contact"
            _leads[uid] = lead
            await msg.reply_text(strings(_lang()).ask_contact)
            return

        if lead.step == "contact":
            lead.contact = text
            lead.step = "comment"
            _leads[uid] = lead
            await msg.reply_text(strings(_lang()).ask_comment)
            return

        if lead.step == "comment":
            lead.comment = text
            _leads.pop(uid, None)

            # notify manager
            if config.MANAGER_CHAT_ID:
                try:
                    chat_id = int(config.MANAGER_CHAT_ID)
                    pkg = PACKAGES.get(lead.package_name, {})
                    price = pkg.get("price", "")
                    time_ = pkg.get("time", "")
                    notify = (
                        "<b>🆕 Новая заявка</b>\n"
                        f"<b>Бренд:</b> {_esc(config.BRAND_NAME)}\n"
                        f"<b>Пакет:</b> {_esc(lead.package_name)} ({_esc(price)} / {_esc(time_)})\n"
                        f"<b>Имя:</b> {_esc(lead.name)}\n"
                        f"<b>Контакт:</b> {_esc(lead.contact)}\n"
                        f"<b>Комментарий:</b>\n{_esc(lead.comment)}\n\n"
                        f"<b>От:</b> @{_esc(update.effective_user.username or '—')} / id={update.effective_user.id}"
                    )
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=notify,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
                except Exception:
                    pass

            await msg.reply_text(strings(_lang()).sent_ok, reply_markup=menu_kb())
            return

    # AI or fallback-to-manager
    if config.OPENROUTER_API_KEY:
        try:
            reply = await ask_openrouter(text)
            reply = (reply or "").strip()
            if len(reply) > MAX_AI_REPLY:
                reply = reply[:MAX_AI_REPLY]
            if reply:
                await msg.reply_text(reply)
                return
        except Exception:
            pass

    # fallback: forward question to manager
    if config.MANAGER_CHAT_ID:
        try:
            chat_id = int(config.MANAGER_CHAT_ID)
            notify = (
                "<b>🆕 Вопрос</b>\n"
                f"<b>От:</b> @{_esc(update.effective_user.username or '—')} / id={update.effective_user.id}\n\n"
                f"{_esc(text)}"
            )
            await context.bot.send_message(chat_id=chat_id, text=notify, parse_mode=ParseMode.HTML)
        except Exception:
            pass

    await msg.reply_text(strings(_lang()).sent_ok_alt, reply_markup=menu_kb())
