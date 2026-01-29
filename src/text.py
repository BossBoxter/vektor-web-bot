# src/text.py
from dataclasses import dataclass


@dataclass(frozen=True)
class Strings:
    start_title: str
    start_body: str
    choose_package: str
    back: str
    ask_name: str
    ask_contact: str
    ask_comment: str
    sent_ok: str
    sent_ok_alt: str
    too_long: str
    ai_disabled: str


_RU = Strings(
    start_title="Привет. Я бот бренда",
    start_body="Выберите пакеты или напишите вопрос.",
    choose_package="Выберите пакет:",
    back="Назад",
    ask_name="Напишите ваше имя.",
    ask_contact="Напишите контакт для связи (Telegram/телефон/почта).",
    ask_comment="Коротко опишите задачу.",
    sent_ok="Заявка отправлена. Менеджер свяжется с вами.",
    sent_ok_alt="Сообщение отправлено менеджеру. Он свяжется с вами.",
    too_long="Слишком длинное сообщение.",
    ai_disabled="AI сейчас отключен.",
)

_EN = Strings(
    start_title="Hi. I am the bot of",
    start_body="Choose packages or ask a question.",
    choose_package="Choose a package:",
    back="Back",
    ask_name="Type your name.",
    ask_contact="Type your contact (Telegram/phone/email).",
    ask_comment="Describe your request briefly.",
    sent_ok="Sent. Manager will contact you.",
    sent_ok_alt="Sent to manager. They will contact you.",
    too_long="Message is too long.",
    ai_disabled="AI is disabled.",
)


def strings(lang: str) -> Strings:
    return _EN if (lang or "").lower().startswith("en") else _RU
