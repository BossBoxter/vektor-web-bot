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

_DATA_DIR = Path(os.getenv("BOT_DATA_DIR", "data"))
_LIMITS_FILE = _DATA_DIR / "limits.json"

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


# =========================
# ANTI-GARBAGE / GIBBERISH
# =========================
_RE_LETTER = re.compile(r"[A-Za-zА-Яа-яЁё]")
_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RE_PHONE = re.compile(r"^\+?\d[\d\-\s\(\)]{6,}$")
_RE_TG = re.compile(r"^@[\w\d_]{3,}$")

_SPAM_PATTERNS = [
    re.compile(r"(.)\1{5,}"),              # aaaaaa / !!!!!!!
    re.compile(r"^[\W_]+$"),               # only symbols/underscores
    re.compile(r"^(?:[A-Za-z]{1,2}|\d{1,2})$"),  # too short noise
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


def _tokens(s: str) -> list[str]:
    return re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", (s or "").strip())


def _unique_bigram_ratio(s: str) -> float:
    s = re.sub(r"\s+", "", (s or "").lower())
    if len(s) < 8:
        return 1.0
    bigrams = [s[i : i + 2] for i in range(len(s) - 1)]
    if not bigrams:
        return 1.0
    return len(set(bigrams)) / len(bigrams)


def _looks_like_gibberish(s: str) -> bool:
    s = (s or "").strip()
    if len(s) < 8:
        return False

    compact = re.sub(r"\s+", "", s)

    # 1) repeated short chunk: "фыв" * N, "abc" * N
    m = re.match(r"^(.{2,5})\1{3,}$", compact, flags=re.IGNORECASE)
    if m:
        return True

    toks = _tokens(s)

    # 2) one long token without spaces: "фывывфывфывывы..."
    if len(toks) == 1 and len(toks[0]) >= 10:
        tok = toks[0]
        # if no digits and low bigram diversity => syllable spam
        if not any(ch.isdigit() for ch in tok):
            if _unique_bigram_ratio(tok) < 0.35:
                return True

    # 3) one "word" message but long enough: likely random letters
    if len(toks) == 1 and len(compact) >= 18:
        return True

    return False


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

    if _looks_like_gibberish(s):
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
    # require at least 2 tokens (blocks "фывывфывфывы..." and single-word garbage)
    if len(_tokens(c)) < 2:
        return False
    return True


def _esc_html(s: str) -> str:
    return html.escape(s or "", quote=False)


# =========================
# STATE
# =========================
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


def _t() -> dict:
    return strings(_lang())


def _leads_remaining(user_id: int) -> int:
    used = _get_user_leads_used(user_id)
    return max(0, MAX_LEADS_PER_USER - used)


def _lead_allowed(user_id: int) -> bool:
    return _leads_remaining(user_id) > 0


def _lead_gate_text() -> str:
    return _t()["lead_limit_reached"]


def _format_pkg_line(lead: LeadDraft) -> str:
    if lead.package_name == "consult":
        return "Консультация"
    pkg = PACKAGES.get(lead.package_name, {})
    price = pkg.get("price", "")
    time_ = pkg.get("time", "")
    return f"{lead.package_name} ({price} / {time_})" if (price or time_) else lead.package_name


# =========================
# HANDLERS
# =========================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = _t()
    title = t["start_title"]
    body = t["start_body"]
    await update.effective_message.reply_text(
        f"{title}\n\n{body}",
        reply_markup=menu_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_packages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        _t()["choose_package"],
        reply_markup=packages_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    data = q.data or ""
    uid = q.from_user.id
    t = _t()

    if data == "NAV:MENU":
        await q.message.reply_text("**Меню 🏠**", reply_markup=menu_kb(), parse_mode=ParseMode.MARKDOWN)
        await q.answer()
        return

    if data == "NAV:PACKAGES":
        await q.message.reply_text(t["choose_package"], reply_markup=packages_kb(), parse_mode=ParseMode.MARKDOWN)
        await q.answer()
        return

    if data == "NAV:HOW":
        await q.message.reply_text(how_text(), reply_markup=how_kb())
        await q.answer()
        return

    if data == "NAV:CONSULT":
        if not _lead_allowed(uid):
            await q.message.reply_text(_lead_gate_text(), reply_markup=menu_kb(), parse_mode=ParseMode.MARKDOWN)
            await q.answer()
            return
        _leads[uid] = LeadDraft(package_name="consult", step="name")
        await q.message.reply_text(
            t["consult_start"] + "\n\n" + t["ask_name"],
            reply_markup=lead_cancel_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
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
            await q.message.reply_text(_lead_gate_text(), reply_markup=menu_kb(), parse_mode=ParseMode.MARKDOWN)
            await q.answer()
            return

        name = context.user_data.get("selected_package")
        if not name or name not in PACKAGES:
            await q.answer("Сначала выберите вариант", show_alert=True)
            return

        _leads[uid] = LeadDraft(package_name=name, step="name")
        await q.message.reply_text(t["ask_name"], reply_markup=lead_cancel_kb(), parse_mode=ParseMode.MARKDOWN)
        await q.answer()
        return

    if data == "LEAD:CANCEL":
        _leads.pop(uid, None)
        await q.message.reply_text(t["cancelled"], reply_markup=menu_kb(), parse_mode=ParseMode.MARKDOWN)
        await q.answer()
        return

    await q.answer()


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return

    uid = update.effective_user.id
    t = _t()

    # SpamGuard: cooldown/ban
    status, left = _GUARD.on_message(uid)
    if status == "cooldown":
        if _GUARD.should_notice(uid):
            _GUARD._set_notice(uid, int(time.time()))
            await msg.reply_text(t["cooldown_seconds"].format(seconds=left), parse_mode=ParseMode.MARKDOWN)
        return

    if status == "ban":
        if _GUARD.should_notice(uid):
            _GUARD._set_notice(uid, int(time.time()))
            await msg.reply_text(t["hard_block"], parse_mode=ParseMode.MARKDOWN)
        return

    text = (msg.text or "").strip()
    if not text:
        return

    if len(text) > MAX_USER_TEXT:
        await msg.reply_text(t["too_long"], parse_mode=ParseMode.MARKDOWN)
        return

    # Lead flow
    if uid in _leads:
        lead = _leads[uid]

        if lead.step == "name":
            if not _is_valid_name(text):
                await msg.reply_text(t["bad_name"], reply_markup=lead_cancel_kb(), parse_mode=ParseMode.MARKDOWN)
                return
            lead.name = text
            lead.step = "contact"
            _leads[uid] = lead
            await msg.reply_text(t["ask_contact"], reply_markup=lead_cancel_kb(), parse_mode=ParseMode.MARKDOWN)
            return

        if lead.step == "contact":
            if not _is_valid_contact(text):
                await msg.reply_text(t["bad_contact"], reply_markup=lead_cancel_kb(), parse_mode=ParseMode.MARKDOWN)
                return
            lead.contact = text
            lead.step = "comment"
            _leads[uid] = lead
            await msg.reply_text(t["ask_comment"], reply_markup=lead_cancel_kb(), parse_mode=ParseMode.MARKDOWN)
            return

        if lead.step == "comment":
            if not _is_valid_comment(text):
                await msg.reply_text(t["bad_comment"], reply_markup=lead_cancel_kb(), parse_mode=ParseMode.MARKDOWN)
                return

            if not _lead_allowed(uid):
                _leads.pop(uid, None)
                await msg.reply_text(_lead_gate_text(), reply_markup=menu_kb(), parse_mode=ParseMode.MARKDOWN)
                return

            lead.comment = text
            _leads.pop(uid, None)

            # Send target lead to manager
            if config.MANAGER_CHAT_ID:
                try:
                    chat_id = int(config.MANAGER_CHAT_ID)
                    pkg_line = _format_pkg_line(lead)

                    notify = (
                        "<b>🆕 Целевая заявка</b>\n"
                        f"<b>Бренд:</b> {_esc_html(config.BRAND_NAME)}\n"
                        f"<b>Пакет:</b> {_esc_html(pkg_line)}\n"
                        f"<b>Имя:</b> {_esc_html(lead.name)}\n"
                        f"<b>Контакт:</b> {_esc_html(lead.contact)}\n"
                        f"<b>Комментарий:</b>\n{_esc_html(lead.comment)}\n\n"
                        f"<b>От:</b> @{_esc_html(update.effective_user.username or '—')} / id={update.effective_user.id}"
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
                        t["sent_ok"] + f"\n\nОсталось заявок: {remaining}.",
                        reply_markup=menu_kb(),
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception:
                    await msg.reply_text(t["sent_ok"], reply_markup=menu_kb(), parse_mode=ParseMode.MARKDOWN)
            else:
                await msg.reply_text(t["sent_ok"], reply_markup=menu_kb(), parse_mode=ParseMode.MARKDOWN)
            return

    # Not in lead flow: block garbage before manager/AI
    if _is_garbage_text(text):
        await msg.reply_text(t["garbage_text"], reply_markup=menu_kb(), parse_mode=ParseMode.MARKDOWN)
        return

    # Lead limit reached: allow only target question (already validated above)
    if not _lead_allowed(uid):
        if config.MANAGER_CHAT_ID:
            try:
                chat_id = int(config.MANAGER_CHAT_ID)
                notify = (
                    "<b>🆕 Целевой вопрос (лимит заявок исчерпан)</b>\n"
                    f"<b>От:</b> @{_esc_html(update.effective_user.username or '—')} / id={update.effective_user.id}\n\n"
                    f"{_esc_html(text)}"
                )
                await context.bot.send_message(chat_id=chat_id, text=notify, parse_mode=ParseMode.HTML)
            except Exception:
                pass
        await msg.reply_text(t["sent_ok_alt"], reply_markup=menu_kb(), parse_mode=ParseMode.MARKDOWN)
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

    # Fallback: forward as target question (already validated above)
    if config.MANAGER_CHAT_ID:
        try:
            chat_id = int(config.MANAGER_CHAT_ID)
            notify = (
                "<b>🆕 Целевой вопрос</b>\n"
                f"<b>От:</b> @{_esc_html(update.effective_user.username or '—')} / id={update.effective_user.id}\n\n"
                f"{_esc_html(text)}"
            )
            await context.bot.send_message(chat_id=chat_id, text=notify, parse_mode=ParseMode.HTML)
        except Exception:
            pass

    await msg.reply_text(t["sent_ok_alt"], reply_markup=menu_kb(), parse_mode=ParseMode.MARKDOWN)
