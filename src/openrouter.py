import httpx
from .config import config

SYSTEM = (
    "Ты — помощник компании Vektor Web. Отвечай коротко и по делу. "
    "Если вопрос про выбор пакета — предлагай открыть «Пакеты»."
)

async def ask_openrouter(user_text: str) -> str:
    if not config.OPENROUTER_API_KEY:
        return "Напишите вопрос."

    payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.4,
        "max_tokens": 350,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            config.OPENROUTER_API_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://vektor-web.ru",
                "X-Title": "Vektor Web Bot",
            },
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
