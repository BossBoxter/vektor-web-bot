# Vektor Web Bot (Fly.io)

Telegram-бот + API endpoint для заявок с сайта.

## Что работает
- Telegram webhook: `POST /webhook`
- Приём заявок с сайта: `POST /lead` (CORS + OPTIONS)
- Проверка: `GET /health`

## Fly Secrets (обязательные)
- BOT_TOKEN
- WEBHOOK_URL (например: https://vektor-web-bot.fly.dev)
- MANAGER_CHAT_ID (numeric)
- DEBUG=false

## Fly Secrets (для сайта)
- ALLOWED_ORIGINS (через запятую)
  пример: `https://username.github.io,https://vektor-web.ru`
- (опционально) LEAD_SECRET (тогда сайт шлёт header `X-Lead-Secret`)

## Локальный запуск (polling)
- DEBUG=true
- BOT_TOKEN
Команда:
`python -m src.bot`

## Пример запроса с сайта
POST `https://vektor-web-bot.fly.dev/lead`
JSON:
```json
{
  "name": "Антон",
  "contact": "@username / +7...",
  "package": "Профи",
  "message": "Нужен лендинг, сроки 5 дней",
  "page": "https://username.github.io/",
  "utm": {"utm_source":"ads","utm_campaign":"test"},
  "source": "site"
}
