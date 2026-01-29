# src/antispam.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Tuple


def _now() -> float:
    return time.time()


@dataclass
class TokenBucket:
    capacity: float
    refill_per_sec: float
    tokens: float
    updated_at: float

    def allow(self, cost: float = 1.0) -> Tuple[bool, float]:
        """
        Returns (allowed, retry_after_seconds).
        """
        now = _now()
        elapsed = now - self.updated_at
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
            self.updated_at = now

        if self.tokens >= cost:
            self.tokens -= cost
            return True, 0.0

        need = cost - self.tokens
        retry_after = need / self.refill_per_sec if self.refill_per_sec > 0 else 60.0
        return False, max(0.0, retry_after)


class AntiSpam:
    """
    In-memory token buckets.
    Works per-process. After restart, memory resets.
    """

    def __init__(
        self,
        user_capacity: float = 8.0,
        user_refill_per_sec: float = 0.5,   # 1 token / 2 sec
        ip_capacity: float = 30.0,
        ip_refill_per_sec: float = 1.0,     # 1 token / sec
        gc_ttl_sec: int = 3600,
    ):
        self.user_capacity = float(user_capacity)
        self.user_refill_per_sec = float(user_refill_per_sec)
        self.ip_capacity = float(ip_capacity)
        self.ip_refill_per_sec = float(ip_refill_per_sec)
        self.gc_ttl_sec = int(gc_ttl_sec)

        self._users: Dict[int, TokenBucket] = {}
        self._ips: Dict[str, TokenBucket] = {}
        self._last_gc = _now()

    def _gc(self) -> None:
        now = _now()
        if now - self._last_gc < 60:
            return
        self._last_gc = now

        ttl = self.gc_ttl_sec
        self._users = {k: v for k, v in self._users.items() if (now - v.updated_at) < ttl}
        self._ips = {k: v for k, v in self._ips.items() if (now - v.updated_at) < ttl}

    def allow_user(self, user_id: int, cost: float = 1.0) -> Tuple[bool, int]:
        self._gc()
        b = self._users.get(user_id)
        if not b:
            b = TokenBucket(
                capacity=self.user_capacity,
                refill_per_sec=self.user_refill_per_sec,
                tokens=self.user_capacity,
                updated_at=_now(),
            )
            self._users[user_id] = b
        ok, retry = b.allow(cost=cost)
        return ok, int(retry + 0.999)

    def allow_ip(self, ip: str, cost: float = 1.0) -> Tuple[bool, int]:
        self._gc()
        ip = (ip or "").strip() or "unknown"
        b = self._ips.get(ip)
        if not b:
            b = TokenBucket(
                capacity=self.ip_capacity,
                refill_per_sec=self.ip_refill_per_sec,
                tokens=self.ip_capacity,
                updated_at=_now(),
            )
            self._ips[ip] = b
        ok, retry = b.allow(cost=cost)
        return ok, int(retry + 0.999)
