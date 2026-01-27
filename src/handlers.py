import logging
from typing import List, Optional

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .config import config
from .engine import (
    State,
    get_state,
    get_ctx,
    reset,
    start_consult,
    start_order,
    accept_tz,
    accept_contact,
)
from .ui import (
    PACKAGES,
    FINAL_TEXT,
    menu_text,
    menu_kb,
    how_text,
    how_kb,
    packages_kb,
    package_details_kb,
    lead_cancel_kb,
    contacts_reply_kb,
    remove_reply_kb,
    render_package_text,
)
from .openrouter import ask_openrouter
from .ratelimit import check_lead_allowed, mark_lead_submitted, human_left

logger = logging.getLogger(__name__)


def _manager_chat_ids() -> List[int]:
    """
    MANAGER_CHAT_ID поддерживает:
    - одно число: "123"
    - несколько через запятую: "123,456,-100777..."
    """
    raw = (config.MANAGER_CHAT_ID or "").strip()
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    out: List[int] = []
    for p in parts:
        try:
            out.append(int(p))
        except Exception:
            logger.error(f"MANAGER_CHAT_ID contains non-numeric value: {p!r}")
    return out


async def _notify_manager_once(context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    ids = _manager_chat_ids()
    if not ids:
        logger.error("MANAGER_CHAT_ID is not set. Manager notification skipped.")
        return False

    ok_any = False
    for chat_id in ids:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
            ok_any = True
        except TelegramError:
            logger.exception(f"Manager notify failed for chat_id={chat_id}")
        except Exception:
            logger.exception(f"Unexpected error while notifying manager chat_id={chat_id}")

    return ok_any


async def _notify_manager_with_retry(
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    attempt: int = 1,
    max_attempts: int = 3,
):
    ok = await _notify_manager_once(context, text)
    if ok:
        return

    if attempt >= max_attempts:
        logger.error("Manager notify окончательно не удалось отправить (max retries reached).")
        return

    # backoff: 5s, 15s
    delay = 5 if attempt == 1 else 15
    try:
        context.job_queue.run_once(
            callback=lambda job_ctx: _notify_manager_with_retry(
                job_ctx, text, attempt=attempt + 1, max_attempts=max_attempts
            ),
            when=delay,
            data=None,
            name=f"notify_manager_retry_{attempt}",
        )
        logger.error(f"Manager notify scheduled retry attempt={attempt+1} in {delay}s")
    except Exception:
        logger.exception("Failed to schedule retry via job_queue")


def _user_label(user) -> str:
    return f"@{user.username}" if user.username else f"ID:{user.id}"


async def _blocked_lead_reply(message, seconds_left: int):
    t = human_left(seconds_left)
    txt = (
        "Вы уже оставляли заявку.\n\n"
        f"Повторно можно через {t} или через поддержку: {config.SUPPORT_TG}"
    )
    await message.reply_text(txt, reply_markup=menu_kb())
    await message.reply_text(" ", reply_markup=remove_reply_kb())


async def _finalize_and_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    ЕДИНАЯ точка финала:
    - отправляет FINAL_TEXT клиенту
    - уведомляет менеджера (с ретраями)
    - ставит блокировку на 24ч
    - сбрасывает состояние
    """
    user = update.effective_user
    ctx = get_ctx(context.user_data)

    # 1) Клиенту
    await update.effective_message.reply_text(FINAL_TEXT, reply_markup=menu_kb())
    await update.effective_message.reply_text(" ", reply_markup=remove_reply_kb())

    # 2) Менеджеру (всегда пробуем)
    manager_text = "\n".join([
        "🧾 Новая заявка",
        f"👤 {_user_label(user)}",
        f"📦 Пакет: {ctx.package_name or 'не выбран (консультация)'}",
        f"📝 ТЗ: {ctx.tz or ''}",
        f"📞 Контакт: {ctx.contact or ''}",
    ])
    await _notify_manager_with_retry(context, manager_text)

    # 3) Блокировка на 24ч
    await mark_lead_submitted(user.id)

    # 4) Сброс
    reset(context.user_data)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset(context.user_data)
    await update.message.reply_text(menu_text(), reply_markup=menu_kb())
    await update.message.reply_text(" ", reply_markup=remove_reply_kb())


async def cmd_packages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите пакет:", reply_markup=packages_kb())
    await update.message.reply_text(" ", reply_markup=remove_reply_kb())


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    user = update.effective_user

    if data == "NAV:MENU":
        reset(context.user_data)
        await q.message.edit_text(menu_text(), reply_markup=menu_kb())
        await q.answer()
        return

    if data == "NAV:PACKAGES":
        await q.message.edit_text("Выберите пакет:", reply_markup=packages_kb())
        await q.answer()
        return

    if data == "NAV:HOW":
        await q.message.edit_text(how_text(), reply_markup=how_kb())
        await q.answer()
        return

    if data == "NAV:CONSULT":
        allowed, left = await check_lead_allowed(user.id)
        if not allowed:
            await _blocked_lead_reply(q.message, left)
            await q.answer()
            return

        start_consult(context.user_data)
        await q.message.reply_text(
            "Опишите проект одним сообщением (что нужно сделать, примеры, сроки).",
            reply_markup=lead_cancel_kb(),
        )
        await q.answer()
        return

    if data.startswith("PKG:"):
        name = data.replace("PKG:", "", 1)
        if name not in PACKAGES:
            await q.answer("Пакет не найден")
            return

        ctx = get_ctx(context.user_data)
        ctx.package_name = name

        text = render_package_text(name)
        await q.message.edit_text(text, parse_mode="HTML", reply_markup=package_details_kb())
        await q.answer()
        return

    if data == "LEAD:ORDER":
        allowed, left = await check_lead_allowed(user.id)
        if not allowed:
            await _blocked_lead_reply(q.message, left)
            await q.answer()
            return

        ctx = get_ctx(context.user_data)
        if not ctx.package_name:
            await q.answer("Сначала выберите пакет")
            return

        start_order(context.user_data, ctx.package_name)
        await q.message.reply_text(
            f"Заявка на пакет: {ctx.package_name}\n\nНапишите ТЗ одним сообщением.",
            reply_markup=lead_cancel_kb(),
        )
        await q.answer()
        return

    if data == "LEAD:CANCEL":
        reset(context.user_data)
        await q.message.reply_text("Отменено.", reply_markup=menu_kb())
        await q.message.reply_text(" ", reply_markup=remove_reply_kb())
        await q.answer()
        return

    await q.answer("Неизвестное действие")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (update.message.text or "").strip()

    if text == "❌ Отмена":
        reset(context.user_data)
        await update.message.reply_text("Отменено.", reply_markup=menu_kb())
        await update.message.reply_text(" ", reply_markup=remove_reply_kb())
        return

    state = get_state(context.user_data)

    if text == "⬅️ Назад" and state == State.LEAD_CONTACT:
        context.user_data["state"] = State.LEAD_TZ.value
        await update.message.reply_text("Ок. Снова напишите ТЗ одним сообщением.", reply_markup=remove_reply_kb())
        return

    if state == State.LEAD_TZ:
        accept_tz(context.user_data, text)
        msg = (
            "Принято.\n\n"
            "Теперь оставьте контакт для связи одним сообщением:\n"
            "• ваш @telegram (можно нажать кнопку)\n"
            "• или телефон\n"
            "• или email"
        )
        await update.message.reply_text(msg, reply_markup=contacts_reply_kb(user.username, user.id))
        return

    if state == State.LEAD_CONTACT:
        accept_contact(context.user_data, text)
        await _finalize_and_notify(update, context)
        return

    resp = await ask_openrouter(text)
    await update.message.reply_text(resp, reply_markup=remove_reply_kb())
