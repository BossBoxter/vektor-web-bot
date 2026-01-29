from telegram import InlineKeyboardButton, InlineKeyboardMarkup

SUPPORT_URL = "https://t.me/bloknotpr"

# =========================
# ПАКЕТЫ
# =========================
PACKAGES = {
    "Быстрый запуск": {
        "button": "🚀 Быстрый запуск — заявки",
        "price": "10 000 ₽",
        "time": "1–2 дня",
        "fits": [
            "нужно запустить оффер быстро",
            "важен простой понятный лендинг",
            "нужны заявки в Telegram",
        ],
        "result": "Лендинг + приём заявок в Telegram.",
        "desc": "Минимум лишнего. Чёткая структура. Быстрый результат.",
        "features": [
            "1 страница (до 6 блоков)",
            "Форма заявки",
            "Адаптив под мобильные",
            "Базовая SEO-разметка",
            "Публикация сайта",
        ],
    },
    "Личный бренд": {
        "button": "👤 Личный бренд — доверие",
        "price": "25 000 ₽",
        "time": "3–5 дней",
        "fits": [
            "вы эксперт / специалист / блогер",
            "нужна упаковка и доверие",
            "нужны заявки и понятная структура",
        ],
        "result": "Сайт-визитка + заявки.",
        "desc": "Сайт, который объясняет кто вы, что делаете и как записаться.",
        "features": [
            "До 10 блоков",
            "Обо мне, услуги, кейсы, отзывы",
            "2 формы связи",
            "Адаптив + оптимизация скорости",
            "Инструкция по редактированию",
        ],
    },
    "Продающий лендинг": {
        "button": "💰 Продажи — конверсия",
        "price": "50 000 ₽",
        "time": "5–9 дней",
        "fits": [
            "планируется реклама",
            "нужен поток заявок",
            "важны смыслы и структура под конверсию",
        ],
        "result": "Лендинг под конверсию + заявки в Telegram.",
        "desc": "Фокус на результате: оффер → доверие → действие → заявки.",
        "features": [
            "Прототип структуры",
            "Лендинг или лендинг + спасибо",
            "Лид-магнит или мини-квиз (по ситуации)",
            "Интеграция заявок в Telegram",
            "Аналитика и события",
        ],
    },
    "Магазин / каталог": {
        "button": "🛒 Каталог — заказы",
        "price": "100 000 ₽",
        "time": "10–14 дней",
        "fits": [
            "нужно показать товары",
            "нужно собирать заказы/заявки",
            "важна простая структура без сложности ERP",
        ],
        "result": "Каталог товаров + приём заказов.",
        "desc": "Показать ассортимент и не терять заявки/заказы.",
        "features": [
            "Каталог до 30 товаров",
            "Карточки товаров",
            "Форма заказа / заявки",
            "Интеграция в Telegram",
            "Инструкция по обновлению",
        ],
    },
    "Автоматизация + бот": {
        "button": "🤖 Автоматизация — бот",
        "price": "125 000 ₽",
        "time": "14–21 день",
        "fits": [
            "заявки теряются",
            "нужно меньше ручной работы",
            "нужен сценарий: вопросы → контакт → заявка",
        ],
        "result": "Сайт + Telegram-бот под сценарий.",
        "desc": "Автоприём заявок, сбор данных, уведомления менеджеру.",
        "features": [
            "Лендинг",
            "Telegram-бот со сценарием",
            "Сбор контактов и ТЗ",
            "Уведомления менеджеру",
            "Запуск и инструкция",
        ],
    },
    "Индивидуальный проект": {
        "button": "🧩 Индивидуально — интеграции",
        "price": "от 200 000 ₽",
        "time": "от 3–6 недель",
        "fits": [
            "сложные процессы и интеграции",
            "CRM / оплаты / кабинеты",
            "нестандартная логика",
        ],
        "result": "Решение под задачу.",
        "desc": "Когда нужен продукт и архитектура, а не просто лендинг.",
        "features": [
            "Предпроектная аналитика",
            "Техническое задание",
            "Интеграции (CRM, оплаты, сервисы)",
            "Этапы и сроки",
            "Поддержка по договорённости",
        ],
    },
}

# =========================
# ГЛАВНОЕ МЕНЮ: 4 КНОПКИ
# =========================
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подобрать решение", callback_data="NAV:PICK")],
        [InlineKeyboardButton("📦 Пакеты и цены", callback_data="NAV:PACKAGES")],
        [InlineKeyboardButton("📝 Оставить заявку", callback_data="NAV:LEAD")],
        [InlineKeyboardButton("🆘 Вопрос / Поддержка", callback_data="NAV:SUPPORT")],
    ])

def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 В меню", callback_data="NAV:MENU")],
    ])

def support_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🆘 Открыть поддержку", url=SUPPORT_URL)],
        [InlineKeyboardButton("🏠 В меню", callback_data="NAV:MENU")],
    ])

# =========================
# ПАКЕТЫ
# =========================
def packages_kb() -> InlineKeyboardMarkup:
    rows = []
    for name, p in PACKAGES.items():
        rows.append([InlineKeyboardButton(p["button"], callback_data=f"PKG:{name}")])
    rows.append([InlineKeyboardButton("🏠 В меню", callback_data="NAV:MENU")])
    return InlineKeyboardMarkup(rows)

def package_details_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Оформить", callback_data="LEAD:ORDER")],
        [InlineKeyboardButton("📦 Все пакеты", callback_data="NAV:PACKAGES")],
        [InlineKeyboardButton("🏠 В меню", callback_data="NAV:MENU")],
    ])

def lead_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отмена", callback_data="LEAD:CANCEL")],
        [InlineKeyboardButton("🏠 В меню", callback_data="NAV:MENU")],
    ])

# =========================
# ПОДБОР РЕШЕНИЯ: 3 ВОПРОСА
# =========================
def pick_goal_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Запуск быстро", callback_data="PICK:GOAL:FAST")],
        [InlineKeyboardButton("💰 Нужны заявки", callback_data="PICK:GOAL:LEADS")],
        [InlineKeyboardButton("👤 Личный бренд", callback_data="PICK:GOAL:BRAND")],
        [InlineKeyboardButton("🛒 Каталог/магазин", callback_data="PICK:GOAL:SHOP")],
        [InlineKeyboardButton("🤖 Автоматизация", callback_data="PICK:GOAL:AUTO")],
        [InlineKeyboardButton("🏠 В меню", callback_data="NAV:MENU")],
    ])

def pick_deadline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Срочно (1–3 дня)", callback_data="PICK:DEADLINE:URGENT")],
        [InlineKeyboardButton("⏳ Нормально (до 2 недель)", callback_data="PICK:DEADLINE:NORMAL")],
        [InlineKeyboardButton("🗓 Не важно", callback_data="PICK:DEADLINE:ANY")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="PICK:BACK")],
        [InlineKeyboardButton("🏠 В меню", callback_data="NAV:MENU")],
    ])

def pick_budget_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("до 25k", callback_data="PICK:BUDGET:25")],
        [InlineKeyboardButton("до 50k", callback_data="PICK:BUDGET:50")],
        [InlineKeyboardButton("100k+", callback_data="PICK:BUDGET:100")],
        [InlineKeyboardButton("не знаю", callback_data="PICK:BUDGET:UNK")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="PICK:BACK")],
        [InlineKeyboardButton("🏠 В меню", callback_data="NAV:MENU")],
    ])

# =========================
# РЕНДЕР КАРТОЧКИ ПАКЕТА (HTML)
# =========================
def render_package_text(name: str) -> str:
    p = PACKAGES[name]
    fits = "\n".join(f"• {x}" for x in p.get("fits", []))
    features = "\n".join(f"• {f}" for f in p["features"])
    return (
        f"<b>{p['button']}</b>\n\n"
        f"<b>Подойдёт, если:</b>\n{fits}\n\n"
        f"<b>Результат:</b>\n<b>{p['result']}</b>\n\n"
        f"<b>Срок:</b> <b>{p['time']}</b>\n"
        f"<b>Стоимость:</b> <b>{p['price']}</b>\n\n"
        f"<b>Что входит:</b>\n{features}\n\n"
        f"{p['desc']}"
    )
