from __future__ import annotations

import os  # FIX: нужен для os.getenv
from dataclasses import dataclass
from typing import Dict

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .config import config
from .text import strings
from .ai import openrouter_chat

router = Router()

MAX_USER_TEXT = 4000
MAX_AI_REPLY = 3500

LANG_RU = "ru"
LANG_EN = "en"


# ====== Пакеты (пример) ======
PACKAGES = [
    ("p1", "Start — лендинг + базовая интеграция", "Лендинг 1 страница, адаптив, формы, подключение аналитики."),
    ("p2", "Pro — сайт + бот", "Лендинг/сайт, Telegram-бот, заявки, уведомления, интеграции."),
    ("p3", "Business — воронка + CRM", "Сайт + бот + интеграция CRM, платежи, автоворонка."),
    ("p4", "Ecom — каталог/магазин", "Каталог/магазин, корзина, оплата, уведомления, аналитика."),
    ("p5", "Custom — спецпроект", "Нестандартная автоматизация, сложные интеграции, аудит/архитектура."),
]

# FIX: переменная использует os.getenv — теперь os импортирован
AI_ENABLED = (os.getenv("AI_ENABLED", "1").strip() not in ("0", "false", "False", ""))


@dataclass
class LeadDraft:
    package_id: str
    package_title: str
    name: str = ""
    contact: str = ""
    comment: str = ""
    step: str = "name"  # name -> contact -> comment -> done


_leads: Dict[int, LeadDraft] = {}  # key = user_id


def _get_lang(message: Message) -> str:
    lang = config.DEFAULT_LANG
    return lang if lang in (LANG_RU, LANG_EN) else LANG_RU


def _kb_main(lang: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="Пакеты" if lang == "ru" else "Packages", callback_data="packages")
    kb.button(text="AI" if lang == "ru" else "AI", callback_data="ai")
    kb.adjust(2)
    return kb.as_markup()


def _kb_packages(lang: str):
    s = strings(lang)
    kb = InlineKeyboardBuilder()
    for pid, title, _desc in PACKAGES:
        kb.button(text=title, callback_data=f"pkg:{pid}")
    kb.button(text=s.back, callback_data="back")
    kb.adjust(1)
    return kb.as_markup()


def _find_package(pid: str):
    for x in PACKAGES:
        if x[0] == pid:
            return x
    return None


async def _notify_manager(message: Message, lead: LeadDraft) -> None:
    text = (
        f"🆕 Новая заявка\n"
        f"Бренд: {config.BRAND_NAME}\n"
        f"Пакет: {lead.package_title} ({lead.package_id})\n"
        f"Имя: {lead.name}\n"
        f"Контакт: {lead.contact}\n"
        f"Комментарий: {lead.comment}\n\n"
        f"От: @{message.from_user.username or '—'} / id={message.from_user.id}"
    )
    await message.bot.send_message(chat_id=config.MANAGER_CHAT_ID, text=text)


@router.message(CommandStart())
async def cmd_start(message: Message):
    lang = _get_lang(message)
    s = strings(lang)
    title = s.start_title.replace("бот бренда", f"бот бренда {config.BRAND_NAME}")
    body = s.start_body
    await message.answer(f"{title}\n\n{body}", reply_markup=_kb_main(lang))


@router.callback_query()
async def on_callback(cb: CallbackQuery):
    lang = config.DEFAULT_LANG
    s = strings(lang)

    data = cb.data or ""
    if data == "packages":
        await cb.message.answer(s.choose_package, reply_markup=_kb_packages(lang))
        await cb.answer()
        return

    if data == "back":
        await cb.message.answer("Меню:", reply_markup=_kb_main(lang))
        await cb.answer()
        return

    if data == "ai":
        if not (AI_ENABLED and config.OPENROUTER_API_KEY):
            await cb.message.answer(s.ai_disabled)
        else:
            await cb.message.answer("AI включен. Напишите вопрос сообщением.")
        await cb.answer()
        return

    if data.startswith("pkg:"):
        pid = data.split(":", 1)[1].strip()
        pkg = _find_package(pid)
        if not pkg:
            await cb.answer("Не найдено" if lang == "ru" else "Not found", show_alert=True)
            return
        _leads[cb.from_user.id] = LeadDraft(package_id=pkg[0], package_title=pkg[1], step="name")
        await cb.message.answer(s.ask_name)
        await cb.answer()
        return

    await cb.answer()


@router.message()
async def on_text(message: Message):
    lang = _get_lang(message)
    s = strings(lang)

    text = (message.text or "").strip()
    if not text:
        return
    if len(text) > MAX_USER_TEXT:
        await message.answer(s.too_long)
        return

    uid = message.from_user.id

    # Если идет заполнение заявки
    if uid in _leads:
        lead = _leads[uid]

        if lead.step == "name":
            lead.name = text
            lead.step = "contact"
            _leads[uid] = lead
            await message.answer(s.ask_contact)
            return

        if lead.step == "contact":
            lead.contact = text
            lead.step = "comment"
            _leads[uid] = lead
            await message.answer(s.ask_comment)
            return

        if lead.step == "comment":
            lead.comment = text
            lead.step = "done"
            _leads[uid] = lead
            await _notify_manager(message, lead)
            del _leads[uid]
            await message.answer(s.sent_ok)
            return

    # Иначе — обычный вопрос: AI или пересылка менеджеру
    if AI_ENABLED and config.OPENROUTER_API_KEY:
        system_prompt = (
            f"Ты консультант бренда {config.BRAND_NAME}. "
            f"Отвечай кратко и по делу. Если нужно уточнение — скажи, что менеджер свяжется."
        )
        try:
            reply = await openrouter_chat(
                api_key=config.OPENROUTER_API_KEY,
                model=config.OPENROUTER_MODEL,
                user_text=text,
                system_prompt=system_prompt,
            )
            reply = (reply or "").strip()
            if len(reply) > MAX_AI_REPLY:
                reply = reply[:MAX_AI_REPLY]
            if reply:
                await message.answer(reply)
                return
        except Exception:
            pass

    # fallback: переслать менеджеру как "вопрос"
    lead = LeadDraft(package_id="question", package_title="Вопрос", name="—", contact="—", comment=text, step="done")
    await _notify_manager(message, lead)
    await message.answer(s.sent_ok_alt)
