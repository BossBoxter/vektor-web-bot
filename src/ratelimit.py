import time
from typing import Optional, Tuple

from .config import config

try:
    import redis.asyncio as redis_async
except Exception:
    redis_async = None

# Fallback in-memory (не надёжно на Fly при рестартах/нескольких машинах)
_MEM: dict[int, int] = {}


def _now() -> int:
    return int(time.time())


def _key(user_id: int) -> str:
    return f"lead:last:{user_id}"


async def _get_redis():
    if not config.REDIS_URL or not redis_async:
        return None
    return redis_async.from_url(config.REDIS_URL, decode_responses=True)


async def check_lead_allowed(user_id: int) -> Tuple[bool, int]:
    """
    Returns: (allowed, seconds_left)
    allowed=True -> можно создавать новую заявку
    allowed=False -> нельзя, seconds_left показывает сколько ждать
    """
    cooldown = int(config.LEAD_COOLDOWN_SECONDS)
    now = _now()

    r = await _get_redis()
    if r:
        try:
            v = await r.get(_key(user_id))
            last = int(v) if v else 0
            if last and now - last < cooldown:
                return False, cooldown - (now - last)
            return True, 0
        except Exception:
            # fallback
            pass

    last = _MEM.get(user_id, 0)
    if last and now - last < cooldown:
        return False, cooldown - (now - last)
    return True, 0


async def mark_lead_submitted(user_id: int):
    """
    Ставим метку, что заявка создана (и включаем блокировку на 24ч).
    """
    cooldown = int(config.LEAD_COOLDOWN_SECONDS)
    now = _now()

    r = await _get_redis()
    if r:
        try:
            # хранить значение timestamp, TTL = cooldown
            await r.set(_key(user_id), str(now), ex=cooldown)
            return
        except Exception:
            pass

    _MEM[user_id] = now


def human_left(seconds_left: int) -> str:
    if seconds_left <= 0:
        return "0 минут"
    mins = seconds_left // 60
    hours = mins // 60
    mins = mins % 60
    if hours <= 0:
        return f"{mins} мин"
    return f"{hours} ч {mins} мин"
