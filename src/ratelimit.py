import time
from typing import Tuple

from .config import config

# user_id -> unix_ts(last lead submit)
_MEM: dict[int, int] = {}


def _now() -> int:
    return int(time.time())


def human_left(seconds_left: int) -> str:
    if seconds_left <= 0:
        return "0 мин"
    mins = seconds_left // 60
    hours = mins // 60
    mins = mins % 60
    if hours <= 0:
        return f"{mins} мин"
    return f"{hours} ч {mins} мин"


async def check_lead_allowed(user_id: int) -> Tuple[bool, int]:
    cooldown = int(config.LEAD_COOLDOWN_SECONDS)
    now = _now()
    last = _MEM.get(user_id, 0)

    if last and now - last < cooldown:
        return False, cooldown - (now - last)
    return True, 0


async def mark_lead_submitted(user_id: int):
    _MEM[user_id] = _now()
