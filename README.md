# Vektor Web Bot (Fly.io)

Telegram-бот для продажи пакетов и сбора заявок (ТЗ -> контакт -> уведомление менеджеру).

## Переменные окружения (Fly Secrets)

Обязательные:
- BOT_TOKEN
- WEBHOOK_URL (например: https://vektor-web-bot.fly.dev)
- DEBUG=false

Опциональные:
- MANAGER_CHAT_ID (число)
- OPENROUTER_API_KEY
- OPENROUTER_MODEL (например: openai/gpt-4o-mini)

## Локальный запуск (polling)
DEBUG=true и BOT_TOKEN.
