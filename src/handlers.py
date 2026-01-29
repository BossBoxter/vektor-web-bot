# src/handlers.py
from __future__ import annotations

import html
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .config import config
from .openrouter import ask_openrouter
from .spamguard import SpamGuard
from .text import strings
from .ui import (
    PACKAGES,
    menu_kb,
    packages_kb,
    render_package_text,
    package_details_kb,
    how_text,
    how_kb,
    lead_cancel_kb,
)

MAX_USER_TEXT = 4000
MAX_AI_REPLY = 3500

MAX_LEADS_PER_USER = 2

# Persistent counter for leads
_DATA_DIR = Path(os.getenv("BOT_DATA_DIR", "data"))
_LIMITS_FILE = _DATA_DIR / "limits.json"

# Spam guard (persistent bans/cooldowns)
_GUARD = SpamGuard()


def _load_limits() -> dict:
    try:
        if not _LIMITS_FILE.exists():
            return {}
        return json.loads(_LIMITS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_limits(d: dict) -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _LIMITS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_LIMITS_FILE)
    except Exception:
        pass


_LIMITS = _load_limits()


def _user_key(user_id: int) -> str:
    return str(user_id)


def _get_user_leads_used(user_id: int) -> int:
    return int((_LIMITS.get(_user_key(user_id)) or {}).get("leads_used", 0))


def _inc_user_leads_used(user_id: int) -> int:
    k = _user_key(user_id)
    rec = _LIMITS.get(k) or {}
    rec["leads_used"] = int(rec.get("leads_used", 0)) + 1
    rec["updated_at"] = int(time.time())
    _LIMITS[k] = rec
    _save_limits(_LIMITS)
    return int(rec["leads_used"])


# --- garbage filters ---
_RE_LETTER = re.compile(r"[A-Za-zА-Яа-яЁё]")
_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RE_PHONE = re.compile(r"^\+?\d[\d\-\s\(\)]{6,}$")
_RE_TG = re.compile(r"^@[\w\d_]{3,}$")

_SPAM_PATTERNS = [
    re.compile(r"(.)\1{5,}"),
    re.compile(r"^[\W_]+$"),
    re.compile(r"^(?:[A-Za-z]{1,2}|\d{1,2})$"),
]


def _ratio_letters(s: str) -> float:
    if not s:
        return 0.0
    letters = len(_RE_LETTER.findall(s))
    return letters / max(1, len(s))


def _ratio_alnum(s: str) -> float:
    if not s:
        return 0.0
    alnum = sum(ch.isalnum() for ch in s)
    return alnum / max(1, len(s))


def _is_garbage_text(s: str) -> bool:
    s = (s or "").strip()
    if len(s) < 3:
        return True
    if len(s) > 2500:
        return True
    for p in _SPAM_PATTERNS:
        if p.search(s):
            return True
    if _ratio_letters(s) < 0.12 and _ratio_alnum(s) < 0.35:
        return True
    if _ratio_alnum(s) < 0.20 and len(s) > 12:
        return True
    return False


def _is_valid_name(name: str) -> bool:
    name = (name or "").strip()
    if len(name) < 2 or len(name) > 60:
        return False
    if _is_garbage_text(name):
        return False
    if not _RE_LETTER.search(name):
        return False
    if _ratio_letters(name) < 0.25:
        return False
    return True


def _is_valid_contact(contact: str) -> bool:
    c = (contact or "").strip()
    if len(c) < 3 or len(c) > 120:
        return False
    if _is_garbage_text(c):
        return False
    if _RE_TG.match(c):
        return True
    if _RE_EMAIL.match(c):
        return True
    if _RE_PHONE.match(c):
        return True
    if "t.me/" in c or "telegram" in c.lower():
        return True
    return _ratio_alnum(c) >= 0.35


def _is_valid_comment(comment: str) -> bool:
    c = (comment or "").strip()
    if len(c) < 10 or len(c) > 1200:
        return False
    if _is_garbage_text(c):
        return False
    if len(_RE_LETTER.findall(c)) < 6:
        return False
    return True


def _esc(s: str) -> str:
    return html.escape(s or "", quote=False)


# --- lead flow ---
@dataclass
class LeadDraft:
    package_name: str  # key from ui.PACKAGES OR "consult"
    name: str = ""
    contact: str = ""
    comment: str = ""
    step: str = "name"  # name -> contact -> comment


_leads: Dict[int, LeadDraft] = {}


def _lang() -> str:
    return config.DEFAULT_LANG if getattr(config, "DEFAULT_LANG", "ru") in ("ru", "en") else "ru"


def _leads_remaining(user_id: int) -> int:
    used = _get_user_leads_used(user_id)
    return max(0, MAX_LEADS_PER_USER - used)


def _lead_allowed(user_id: int) -> bool:
    return _leads_remaining(user_id) > 0


def _lead_gate_text() -> str:
    return (
        f"Лимит заявок исчерпан ({MAX_LEADS_PER_USER}/{MAX_LEADS_PER_USER}).\n"
        "Доступно: задать нормальный вопрос сообщением или обратиться в поддержку."
    )


def _format_pkg_line(lead: LeadDraft) -> str:
    if lead.package_name == "consult":
        return "Консультация"
    pkg = PACKAGES.get(lead.package_name, {})
    price = pkg.get("price", "")
    time_ = pkg.get("time", "")
    return f"{lead.package_name} ({price} / {time_})" if (price or time_) else lead.package_name


# --- handlers ---
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
    uid = q.from_user.id

    if data == "NAV:MENU":
        await q.message.reply_text("Меню:", reply_markup=menu_kb())
        await q.answer()
        return

    if data == "NAV:PACKAGES":
        await q.message.reply_text(strings(_lang()).choose_package, reply_markup=packages_kb())
        await q.answer()
        return

    if data == "NAV:HOW":
        await q.message.reply_text(how_text(), reply_markup=how_kb())
        await q.answer()
        return

    if data == "NAV:CONSULT":
        if not _lead_allowed(uid):
            await q.message.reply_text(_lead_gate_text(), reply_markup=menu_kb())
            await q.answer()
            return
        _leads[uid] = LeadDraft(package_name="consult", step="name")
        await q.message.reply_text("Консультация.\n\n" + strings(_lang()).ask_name, reply_markup=lead_cancel_kb())
        await q.answer()
        return

    if data.startswith("PKG:"):
        name = data.split(":", 1)[1]
        if name not in PACKAGES:
            await q.answer("Не найдено", show_alert=True)
            return
        await q.message.reply_text(
            render_package_text(name),
            parse_mode=ParseMode.HTML,
            reply_markup=package_details_kb(),
        )
        context.user_data["selected_package"] = name
        await q.answer()
        return

    if data == "LEAD:ORDER":
        if not _lead_allowed(uid):
            await q.message.reply_text(_lead_gate_text(), reply_markup=menu_kb())
            await q.answer()
            return

        name = context.user_data.get("selected_package")
        if not name or name not in PACKAGES:
            await q.answer("Сначала выберите пакет", show_alert=True)
            return
        _leads[uid] = LeadDraft(package_name=name, step="name")
        await q.message.reply_text(strings(_lang()).ask_name, reply_markup=lead_cancel_kb())
        await q.answer()
        return

    if data == "LEAD:CANCEL":
        _leads.pop(uid, None)
        await q.message.reply_text("Отменено.", reply_markup=menu_kb())
        await q.answer()
        return

    await q.answer()


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return

    uid = update.effective_user.id

    # ===== SPAM / COOLDOWN / BAN POLICY =====
    status, left = _GUARD.on_message(uid)
    if status == "cooldown":
        if _GUARD.should_notice(uid):
            _GUARD._set_notice(uid, int(time.time()))
            await msg.reply_text(f"Слишком часто. Подождите {left} сек.")
        return

    if status == "ban":
        if _GUARD.should_notice(uid):
            _GUARD._set_notice(uid, int(time.time()))
            # hour/day text is determined by seconds left, without extra branching
            await msg.reply_text(f"Блокировка за спам. Подождите {left} сек или обратитесь в поддержку.")
        return

    # ===== normal processing =====
    text = (msg.text or "").strip()
    if not text:
        return
    if len(text) > MAX_USER_TEXT:
        await msg.reply_text(strings(_lang()).too_long)
        return

    # lead flow
    if uid in _leads:
        lead = _leads[uid]

        if lead.step == "name":
            if not _is_valid_name(text):
                await msg.reply_text("Имя выглядит как спам/мусор. Введите нормальное имя.", reply_markup=lead_cancel_kb())
                return
            lead.name = text
            lead.step = "contact"
            _leads[uid] = lead
            await msg.reply_text(strings(_lang()).ask_contact, reply_markup=lead_cancel_kb())
            return

        if lead.step == "contact":
            if not _is_valid_contact(text):
                await msg.reply_text("Контакт выглядит как спам/мусор. Введите Telegram @username, телефон или email.", reply_markup=lead_cancel_kb())
                return
            lead.contact = text
            lead.step = "comment"
            _leads[uid] = lead
            await msg.reply_text(strings(_lang()).ask_comment, reply_markup=lead_cancel_kb())
            return

        if lead.step == "comment":
            if not _is_valid_comment(text):
                await msg.reply_text("Описание выглядит как спам/мусор. Напишите нормальным текстом, что нужно сделать.", reply_markup=lead_cancel_kb())
                return

            if not _lead_allowed(uid):
                _leads.pop(uid, None)
                await msg.reply_text(_lead_gate_text(), reply_markup=menu_kb())
                return

            lead.comment = text
            _leads.pop(uid, None)

            # send "target lead" to manager
            if config.MANAGER_CHAT_ID:
                try:
                    chat_id = int(config.MANAGER_CHAT_ID)
                    pkg_line = _format_pkg_line(lead)

                    notify = (
                        "<b>🆕 Целевая заявка</b>\n"
                        f"<b>Бренд:</b> {_esc(config.BRAND_NAME)}\n"
                        f"<b>Пакет:</b> {_esc(pkg_line)}\n"
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
                    used = _inc_user_leads_used(uid)
                    remaining = max(0, MAX_LEADS_PER_USER - used)
                    await msg.reply_text(
                        f"{strings(_lang()).sent_ok}\nОсталось заявок: {remaining}.",
                        reply_markup=menu_kb(),
                    )
                except Exception:
                    await msg.reply_text(strings(_lang()).sent_ok, reply_markup=menu_kb())
            else:
                await msg.reply_text(strings(_lang()).sent_ok, reply_markup=menu_kb())
            return

    # limit reached: only "target question" allowed
    if not _lead_allowed(uid):
        if _is_garbage_text(text):
            await msg.reply_text(_lead_gate_text(), reply_markup=menu_kb())
            return

        if config.MANAGER_CHAT_ID:
            try:
                chat_id = int(config.MANAGER_CHAT_ID)
                notify = (
                    "<b>🆕 Целевой вопрос (лимит заявок исчерпан)</b>\n"
                    f"<b>От:</b> @{_esc(update.effective_user.username or '—')} / id={update.effective_user.id}\n\n"
                    f"{_esc(text)}"
                )
                await context.bot.send_message(chat_id=chat_id, text=notify, parse_mode=ParseMode.HTML)
            except Exception:
                pass
        await msg.reply_text("Вопрос принят. Поддержка/менеджер ответит.", reply_markup=menu_kb())
        return

    # lead still allowed: normal question path, but reject garbage
    if _is_garbage_text(text):
        await msg.reply_text("Сообщение похоже на спам/мусор. Отправьте нормальный вопрос одним сообщением.", reply_markup=menu_kb())
        return

    # AI
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
                "<b>🆕 Целевой вопрос</b>\n"
                f"<b>От:</b> @{_esc(update.effective_user.username or '—')} / id={update.effective_user.id}\n\n"
                f"{_esc(text)}"
            )
            await context.bot.send_message(chat_id=chat_id, text=notify, parse_mode=ParseMode.HTML)
        except Exception:
            pass

    await msg.reply_text(strings(_lang()).sent_ok_alt, reply_markup=menu_kb())
