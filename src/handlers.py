# FILE: src/handlers.py
import logging
from telegram import Update
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


def _manager_chat_id() -> int | None:
    try:
        return int(config.MANAGER_CHAT_ID) if config.MANAGER_CHAT_ID else None
    except Exception:
        return None


async def _notify_manager(context: ContextTypes.DEFAULT_TYPE, text: str):
    """
    Отправляет менеджеру уведомление, если MANAGER_CHAT_ID задан.
    """
    chat_id = _manager_chat_id()
    if not chat_id:
        return
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        logger.error(f"Manager notify failed: {e}")


def _user_label(user) -> str:
    return f"@{user.username}" if user.username else f"ID:{user.id}"


async def _blocked_lead_reply(message, seconds_left: int):
    t = human_left(seconds_left)
    txt = (
        "Вы уже оставляли заявку.\n\n"
        f"Повторно можно через {t} или через поддержку: {config.SUPPORT_TG}"
    )
    await message.reply_text(txt, reply_markup=menu_kb())
    # IMPORTANT FIX: PTB не принимает пробел как текст. Убираем клавиатуру корректно.
    await message.reply_text(".", reply_markup=remove_reply_kb())


async def _finalize_and_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    ЕДИНАЯ точка финала:
    - отправляет FINAL_TEXT клиенту
    - всегда пытается уведомить менеджера
    - ставит блокировку на 24ч
    - сбрасывает состояние
    """
    user = update.effective_user
    ctx = get_ctx(context.user_data)

    # 1) Клиенту (всегда)
    await update.effective_message.reply_text(FINAL_TEXT, reply_markup=menu_kb())
    # IMPORTANT FIX: PTB не принимает пробел как текст. Убираем клавиатуру корректно.
    await update.effective_message.reply_text(".", reply_markup=remove_reply_kb())

    # 2) Менеджеру (всегда пытаемся)
    await _notify_manager(
        context,
        "\n".join(
            [
                "🧾 Новая заявка",
                f"👤 {_user_label(user)}",
                f"📦 Пакет: {ctx.package_name or 'не выбран (консультация)'}",
                f"📝 ТЗ: {ctx.tz or ''}",
                f"📞 Контакт: {ctx.contact or ''}",
            ]
        ),
    )

    # 3) Блокировка на 24ч (фиксируем факт записи)
    await mark_lead_submitted(user.id)

    # 4) Сброс
    reset(context.user_data)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    FIX: поддержка deep-link /start site (переход с сайта)
    Сценарий:
      - /start site -> сразу переводим в консультацию и просим вставить скопированный текст (ТЗ).
      - /start без параметров -> показываем меню.
    """
    reset(context.user_data)

    args = (context.args or [])
    if args and args[0].lower() == "site":
        # Блокируем повторную запись, если уже была (как и в обычной консультации)
        user = update.effective_user
        allowed, left = await check_lead_allowed(user.id)
        if not allowed:
            await _blocked_lead_reply(update.message, left)
            return

        start_consult(context.user_data)
        await update.message.reply_text(
            "Вы пришли с сайта.\n\n"
            "Вставьте скопированное сообщение одним сообщением (ТЗ, примеры, сроки).",
            reply_markup=lead_cancel_kb(),
        )
        await update.message.reply_text(".", reply_markup=remove_reply_kb())
        return

    await update.message.reply_text(menu_text(), reply_markup=menu_kb())
    await update.message.reply_text(".", reply_markup=remove_reply_kb())


async def cmd_packages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите пакет:", reply_markup=packages_kb())
    await update.message.reply_text(".", reply_markup=remove_reply_kb())


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
        await q.message.reply_text(".", reply_markup=remove_reply_kb())
        await q.answer()
        return

    await q.answer("Неизвестное действие")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (update.message.text or "").strip()

    if text == "❌ Отмена":
        reset(context.user_data)
        await update.message.reply_text("Отменено.", reply_markup=menu_kb())
        await update.message.reply_text(".", reply_markup=remove_reply_kb())
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
        accept_contact(cont_
