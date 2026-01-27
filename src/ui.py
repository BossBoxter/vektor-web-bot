from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

PACKAGES = {
    "Мини-сайт": {
        "price": "10 000 ₽",
        "time": "2 дня",
        "desc": "Одна страница, один посыл. Быстрый старт.",
        "features": ["Лендинг из 1 экрана", "1 форма", "Адаптивность", "Хостинг 3 месяца"],
    },
    "Блогер Старт": {
        "price": "25 000 ₽",
        "time": "4 дня",
        "desc": "Визитка в digital-пространстве.",
        "features": ["Сайт-визитка (4 блока)", "Соцсети", "Простая CMS", "Хостинг 1 год"],
    },
    "Профи": {
        "price": "50 000 ₽",
        "time": "5-7 дней",
        "desc": "Инструмент для привлечения клиентов.",
        "features": ["Дизайн до 6 экранов", "Cal.com", "Уведомления", "Базовое SEO", "Хостинг 2 года"],
    },
    "Бизнес-Лендинг": {
        "price": "75 000 ₽",
        "time": "7-10 дней",
        "desc": "Продающий сайт под продукт/услугу.",
        "features": ["Прототипирование", "2 структуры A/B", "Анимации", "Лид-магниты", "GA/Метрика", "Хостинг 3 года"],
    },
    "Магазин": {
        "price": "100 000 ₽",
        "time": "10-14 дней",
        "desc": "Небольшой e-com под ассортимент.",
        "features": ["Каталог до 30", "Фильтры", "Админка заказов", "Оплата", "Интеграции", "Хостинг 3 года"],
    },
    "Автоматизация": {
        "price": "125 000 ₽",
        "time": "14-18 дней",
        "desc": "Сайт + бот: полный цикл.",
        "features": ["Бот", "Корзина/оплата", "Синхронизация", "Триггеры", "Обучение", "Гарантия"],
    },
    "Портфолио Pro": {
        "price": "150 000 ₽",
        "time": "18-25 дней",
        "desc": "Эксклюзивное представительство.",
        "features": ["Уникальный дизайн", "Фильтры", "Behance/Dribbble", "Блог", "SEO", "Поддержка"],
    },
    "Индивидуальное решение": {
        "price": "от 200 000 ₽",
        "time": "от 30 дней",
        "desc": "Разработка с нуля под процессы.",
        "features": ["Веб-приложения", "CRM/ERP", "Нестандарт", "Анализ/UX", "SLA"],
    },
}

FINAL_TEXT = "Передал информацию менеджеру, в ближайшие 5 минут с вами свяжется менеджер для уточнения деталей."

def menu_text() -> str:
    return "Vektor Web — сайты и Telegram-боты под задачу.\n\nВыберите действие кнопками ниже или напишите вопрос."

def how_text() -> str:
    return (
        "Как мы работаем:\n\n"
        "1) Вы выбираете пакет или оставляете заявку на консультацию\n"
        "2) Пишете ТЗ одним сообщением (что нужно сделать, примеры, сроки)\n"
        "3) Оставляете контакт для связи\n"
        "4) Менеджер связывается, уточняет детали, фиксирует стоимость/сроки\n"
        "5) Оплата и старт работ\n\n"
        "Важно: стоимость и сроки финально подтверждает менеджер после уточнения ТЗ."
    )

def menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Пакеты", callback_data="NAV:PACKAGES")],
        [InlineKeyboardButton("📝 Бесплатная консультация", callback_data="NAV:CONSULT")],
        [InlineKeyboardButton("ℹ️ Как мы работаем?", callback_data="NAV:HOW")],
        [InlineKeyboardButton("🆘 Поддержка", url="https://t.me/bloknotpr")],
    ])

def how_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Меню", callback_data="NAV:MENU")],
        [InlineKeyboardButton("📦 Пакеты", callback_data="NAV:PACKAGES")],
        [InlineKeyboardButton("🆘 Поддержка", url="https://t.me/bloknotpr")],
    ])

def packages_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(name, callback_data=f"PKG:{name}")] for name in PACKAGES.keys()]
    rows.append([InlineKeyboardButton("🏠 Меню", callback_data="NAV:MENU")])
    return InlineKeyboardMarkup(rows)

def package_details_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Оформить заказ", callback_data="LEAD:ORDER")],
        [InlineKeyboardButton("⬅️ Назад к пакетам", callback_data="NAV:PACKAGES")],
        [InlineKeyboardButton("🏠 Меню", callback_data="NAV:MENU")],
        [InlineKeyboardButton("🆘 Поддержка", url="https://t.me/bloknotpr")],
    ])

def lead_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отмена", callback_data="LEAD:CANCEL")],
        [InlineKeyboardButton("🏠 Меню", callback_data="NAV:MENU")],
        [InlineKeyboardButton("🆘 Поддержка", url="https://t.me/bloknotpr")],
    ])

def contacts_reply_kb(username: str | None, user_id: int) -> ReplyKeyboardMarkup:
    tag = f"@{username}" if username else f"ID:{user_id}"
    return ReplyKeyboardMarkup(
        [[KeyboardButton(tag)], [KeyboardButton("⬅️ Назад"), KeyboardButton("❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите кнопку или напишите контакт",
    )

def remove_reply_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
