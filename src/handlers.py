from __future__ import annotations

import html
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .config import config
from .openrouter import ask_openrouter
from .spamguard import SpamGuard
from .text import strings
from .ui import (
    PACKAGES,
    main_menu_kb,
    back_to_menu_kb,
    support_kb,
    packages_kb,
    package_details_kb,
    lead_cancel_kb,
    pick_goal_kb,
    pick_deadline_kb,
    pick_budget_kb,
    render_package_text,
)

MAX_USER_TEXT = 4000
MAX_AI_REPLY = 3500
MAX_LEADS_PER_USER = 2

MIN_GENERAL_TEXT = 15
MIN_NAME_TEXT = 2
MIN_CONTACT_TEXT = 3
MIN_TASK_TEXT = 30

_DATA_DIR = Path(os.getenv("BOT_DATA_DIR", "data"))
_LIMITS_FILE = _DATA_DIR / "limits.json"

_GUARD = SpamGuard()

# user_data keys
K_SELECTED_PACKAGE = "selected_package"
K_PICK = "pick_state"          # dict(goal, deadline, budget)
K_PICK_STEP = "pick_step"      # goal|deadline|budget

# =========================
# limits persistence
# =========================
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

def _leads_remaining(user_id: int) -> int:
    return max(0, MAX_LEADS_PER_USER - _get_user_leads_used(user_id))

def _lead_allowed(user_id: int) -> bool:
    return _leads_remaining(user_id) > 0

# =========================
# anti-garbage / validation
# =========================
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
    if re.match(r"^(.{2,5})\1{3,}$", compact, flags=re.IGNORECASE):
        return True
    toks = _tokens(s)
    if len(toks) == 1 and len(toks[0]) >= 10:
        tok = toks[0]
        if not any(ch.isdigit() for ch in tok) and _unique_bigram_ratio(tok) < 0.35:
            return True
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
    if len(_tokens(c)) < 2:
        return False
    return True

def _esc_html(s: str) -> str:
    return html.escape(s or "", quote=False)

# =========================
# strings
# =========================
def _lang() -> str:
    return config.DEFAULT_LANG if getattr(config, "DEFAULT_LANG", "ru") in ("ru", "en") else "ru"

def _t() -> dict:
    return strings(_lang())

# =========================
# lead state
# =========================
@dataclass
class LeadDraft:
    package_name: str  # "unknown" or a key from PACKAGES
    name: str = ""
    contact: str = ""
    comment: str = ""
    step: str = "name"  # name -> contact -> comment

_leads: Dict[int, LeadDraft] = {}

# =========================
# recommender
# =========================
def _recommend(goal: str, deadline: str, budget: str) -> str:
    # приоритеты: срочность и бюджет сильнее всего
    if goal == "SHOP":
        return "Магазин / каталог"
    if goal == "AUTO":
        return "Автоматизация + бот"

    if deadline == "URGENT":
        return "Быстрый запуск"

    if goal == "BRAND":
        if budget in ("25", "50", "UNK"):
            return "Личный бренд"
        return "Индивидуальный проект"

    # goal == LEADS or FAST
    if budget == "25":
        return "Быстрый запуск"
    if budget == "50":
        return "Продающий лендинг"
    if budget == "100":
        return "Индивидуальный проект"
    return "Продающий лендинг"

def _pick_reset(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(K_PICK, None)
    context.user_data.pop(K_PICK_STEP, None)

def _pick_get(context: ContextTypes.DEFAULT_TYPE) -> dict:
    d = context.user_data.get(K_PICK)
    if not isinstance(d, dict):
        d = {"goal": "", "deadline": "", "budget": ""}
        context.user_data[K_PICK] = d
    return d

# =========================
# commands
# =========================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = _t()
    _pick_reset(context)
    _leads.pop(update.effective_user.id, None)
    await update.effective_message.reply_text(
        f"{t['start_title']}\n\n{t['start_body']}",
        reply_markup=main_menu_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )

async def cmd_packages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = _t()
    await update.effective_message.reply_text(
        t["packages_title"],
        reply_markup=packages_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )

# =========================
# callbacks
# =========================
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    uid = q.from_user.id
    t = _t()
    data = q.data or ""

    if data == "NAV:MENU":
        _pick_reset(context)
        _leads.pop(uid, None)
        await q.message.reply_text(
            f"{t['start_title']}\n\n{t['start_body']}",
            reply_markup=main_menu_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        await q.answer()
        return

    if data == "NAV:PICK":
        _pick_reset(context)
        context.user_data[K_PICK_STEP] = "goal"
        await q.message.reply_text(
            t["pick_intro"] + "\n\n" + t["pick_q_goal"],
            reply_markup=pick_goal_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        await q.answer()
        return

    if data == "NAV:PACKAGES":
        await q.message.reply_text(
            t["packages_title"],
            reply_markup=packages_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        await q.answer()
        return

    if data == "NAV:LEAD":
        if not _lead_allowed(uid):
            await q.message.reply_text(t["lead_limit_reached"], reply_markup=support_kb(), parse_mode=ParseMode.MARKDOWN)
            await q.answer()
            return
        _pick_reset(context)
        _leads[uid] = LeadDraft(package_name="unknown", step="name")
        await q.message.reply_text(t["lead_start"] + "\n\n" + t["ask_name"], reply_markup=lead_cancel_kb(), parse_mode=ParseMode.MARKDOWN)
        await q.answer()
        return

    if data == "NAV:SUPPORT":
        await q.message.reply_text(t["support_text"], reply_markup=support_kb(), parse_mode=ParseMode.MARKDOWN)
        await q.answer()
        return

    if data == "LEAD:CANCEL":
        _leads.pop(uid, None)
        await q.message.reply_text(t["cancelled"], reply_markup=main_menu_kb(), parse_mode=ParseMode.MARKDOWN)
        await q.answer()
        return

    # picker back
    if data == "PICK:BACK":
        step = str(context.user_data.get(K_PICK_STEP) or "goal")
        if step == "deadline":
            context.user_data[K_PICK_STEP] = "goal"
            await q.message.reply_text(t["pick_q_goal"], reply_markup=pick_goal_kb(), parse_mode=ParseMode.MARKDOWN)
            await q.answer()
            return
        if step == "budget":
            context.user_data[K_PICK_STEP] = "deadline"
            await q.message.reply_text(t["pick_q_deadline"], reply_markup=pick_deadline_kb(), parse_mode=ParseMode.MARKDOWN)
            await q.answer()
            return
        await q.message.reply_text(
            f"{t['start_title']}\n\n{t['start_body']}",
            reply_markup=main_menu_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        await q.answer()
        return

    # picker answers
    if data.startswith("PICK:GOAL:"):
        goal = data.split(":", 2)[2]
        d = _pick_get(context)
        d["goal"] = goal
        context.user_data[K_PICK_STEP] = "deadline"
        await q.message.reply_text(t["pick_q_deadline"], reply_markup=pick_deadline_kb(), parse_mode=ParseMode.MARKDOWN)
        await q.answer()
        return

    if data.startswith("PICK:DEADLINE:"):
        deadline = data.split(":", 2)[2]
        d = _pick_get(context)
        d["deadline"] = deadline
        context.user_data[K_PICK_STEP] = "budget"
        await q.message.reply_text(t["pick_q_budget"], reply_markup=pick_budget_kb(), parse_mode=ParseMode.MARKDOWN)
        await q.answer()
        return

    if data.startswith("PICK:BUDGET:"):
        budget = data.split(":", 2)[2]
        d = _pick_get(context)
        d["budget"] = budget
        rec = _recommend(d["goal"], d["deadline"], d["budget"])
        if rec not in PACKAGES:
            rec = "Индивидуальный проект"
        context.user_data[K_SELECTED_PACKAGE] = rec
        _pick_reset(context)
        await q.message.reply_text(
            t["pick_done"],
            reply_markup=back_to_menu_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        await q.message.reply_text(
            render_package_text(rec),
            parse_mode=ParseMode.HTML,
            reply_markup=package_details_kb(),
        )
        await q.answer()
        return

    # package open
    if data.startswith("PKG:"):
        name = data.split(":", 1)[1]
        if name not in PACKAGES:
            await q.answer("Не найдено", show_alert=True)
            return
        context.user_data[K_SELECTED_PACKAGE] = name
        await q.message.reply_text(
            render_package_text(name),
            parse_mode=ParseMode.HTML,
            reply_markup=package_details_kb(),
        )
        await q.answer()
        return

    # order from package card
    if data == "LEAD:ORDER":
        if not _lead_allowed(uid):
            await q.message.reply_text(t["lead_limit_reached"], reply_markup=support_kb(), parse_mode=ParseMode.MARKDOWN)
            await q.answer()
            return

        pkg = context.user_data.get(K_SELECTED_PACKAGE)
        pkg = pkg if isinstance(pkg, str) and pkg in PACKAGES else "unknown"
        _leads[uid] = LeadDraft(package_name=pkg, step="name")
        await q.message.reply_text(t["ask_name"], reply_markup=lead_cancel_kb(), parse_mode=ParseMode.MARKDOWN)
        await q.answer()
        return

    await q.answer()

# =========================
# text messages
# =========================
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return

    uid = update.effective_user.id
    t = _t()

    status, left = _GUARD.on_message(uid)
    if status == "cooldown":
        if _GUARD.should_notice(uid):
            _GUARD._set_notice(uid, int(time.time()))
            await msg.reply_text(t["cooldown_seconds"].format(seconds=left), parse_mode=ParseMode.MARKDOWN)
        return

    if status == "ban":
        if _GUARD.should_notice(uid):
            _GUARD._set_notice(uid, int(time.time()))
            await msg.reply_text(t["hard_block"], reply_markup=support_kb(), parse_mode=ParseMode.MARKDOWN)
        return

    text = (msg.text or "").strip()
    if not text:
        return

    if len(text) > MAX_USER_TEXT:
        await msg.reply_text(t["too_long"], parse_mode=ParseMode.MARKDOWN)
        return

    # lead flow
    if uid in _leads:
        lead = _leads[uid]

        if lead.step == "name":
            if len(text) < MIN_NAME_TEXT:
                await msg.reply_text(t["too_short_name"], reply_markup=lead_cancel_kb(), parse_mode=ParseMode.MARKDOWN)
                return
            if not _is_valid_name(text):
                await msg.reply_text(t["bad_name"], reply_markup=lead_cancel_kb(), parse_mode=ParseMode.MARKDOWN)
                return
            lead.name = text
            lead.step = "contact"
            _leads[uid] = lead
            await msg.reply_text(t["ask_contact"], reply_markup=lead_cancel_kb(), parse_mode=ParseMode.MARKDOWN)
            return

        if lead.step == "contact":
            if len(text) < MIN_CONTACT_TEXT:
                await msg.reply_text(t["too_short_contact"], reply_markup=lead_cancel_kb(), parse_mode=ParseMode.MARKDOWN)
                return
            if not _is_valid_contact(text):
                await msg.reply_text(t["bad_contact"], reply_markup=lead_cancel_kb(), parse_mode=ParseMode.MARKDOWN)
                return
            lead.contact = text
            lead.step = "comment"
            _leads[uid] = lead
            await msg.reply_text(t["ask_comment"], reply_markup=lead_cancel_kb(), parse_mode=ParseMode.MARKDOWN)
            return

        if lead.step == "comment":
            if len(text) < MIN_TASK_TEXT:
                await msg.reply_text(t["too_short_task"], reply_markup=lead_cancel_kb(), parse_mode=ParseMode.MARKDOWN)
                return
            if not _is_valid_comment(text):
                await msg.reply_text(t["bad_comment"], reply_markup=lead_cancel_kb(), parse_mode=ParseMode.MARKDOWN)
                return

            if not _lead_allowed(uid):
                _leads.pop(uid, None)
                await msg.reply_text(t["lead_limit_reached"], reply_markup=support_kb(), parse_mode=ParseMode.MARKDOWN)
                return

            lead.comment = text
            _leads.pop(uid, None)

            if config.MANAGER_CHAT_ID:
                try:
                    chat_id = int(config.MANAGER_CHAT_ID)
                    pkg_line = lead.package_name if lead.package_name != "unknown" else "Не выбран"
                    notify = (
                        "<b>🆕 Целевая заявка</b>\n"
                        f"<b>Бренд:</b> {html.escape(config.BRAND_NAME, quote=False)}\n"
                        f"<b>Пакет:</b> {html.escape(pkg_line, quote=False)}\n"
                        f"<b>Имя:</b> {html.escape(lead.name, quote=False)}\n"
                        f"<b>Контакт:</b> {html.escape(lead.contact, quote=False)}\n"
                        f"<b>Задача:</b>\n{html.escape(lead.comment, quote=False)}\n\n"
                        f"<b>От:</b> @{html.escape(update.effective_user.username or '—', quote=False)} / id={update.effective_user.id}"
                    )
                    await context.bot.send_message(chat_id=chat_id, text=notify, parse_mode=ParseMode.HTML)
                    used = _inc_user_leads_used(uid)
                    remaining = max(0, MAX_LEADS_PER_USER - used)
                    await msg.reply_text(
                        t["sent_ok"] + f"\n\nОсталось заявок: {remaining}.",
                        reply_markup=main_menu_kb(),
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception:
                    await msg.reply_text(t["sent_ok"], reply_markup=main_menu_kb(), parse_mode=ParseMode.MARKDOWN)
            else:
                await msg.reply_text(t["sent_ok"], reply_markup=main_menu_kb(), parse_mode=ParseMode.MARKDOWN)
            return

    # outside lead flow
    if len(text) < MIN_GENERAL_TEXT:
        await msg.reply_text(t["too_short_general"], reply_markup=main_menu_kb(), parse_mode=ParseMode.MARKDOWN)
        return

    if _is_garbage_text(text):
        await msg.reply_text(t["garbage_text"], reply_markup=main_menu_kb(), parse_mode=ParseMode.MARKDOWN)
        return

    # if lead limit reached: only questions/support
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
        await msg.reply_text(t["sent_ok_alt"], reply_markup=main_menu_kb(), parse_mode=ParseMode.MARKDOWN)
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

    # fallback to manager
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

    await msg.reply_text(t["sent_ok_alt"], reply_markup=main_menu_kb(), parse_mode=ParseMode.MARKDOWN)
