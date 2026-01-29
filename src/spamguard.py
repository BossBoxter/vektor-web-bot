# src/spamguard.py
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

# Policy (as requested)
SPAM_INTERVAL_SEC = 2          # "1 message in 2 seconds or more often" = spam
SPAM_HITS_TO_COOLDOWN = 3      # after 3 spam hits -> cooldown
COOLDOWN_SEC = 15              # cooldown duration
VIOLATIONS_TO_HOUR_BAN = 5     # after 5 violations -> 1 hour ban
HOUR_BAN_SEC = 60 * 60
DAY_BAN_SEC = 24 * 60 * 60

# Notice throttling (avoid bot answering on every spam message)
NOTICE_COOLDOWN_SEC = 5

DATA_DIR = Path("data")
STATE_FILE = DATA_DIR / "abuse_state.json"


def _now() -> int:
    return int(time.time())


@dataclass
class UserState:
    last_msg_ts: int = 0
    spam_hits: int = 0          # consecutive spam hits (delta <= 2 sec)
    violations: int = 0         # counts when cooldown is applied or user spams during cooldown
    cooldown_until: int = 0     # unix ts
    ban_until: int = 0          # unix ts
    ban_level: int = 0          # 0 none, 1 hour, 2 day
    last_notice_ts: int = 0     # unix ts


class SpamGuard:
    """
    Pure code, GitHub-only.
    Persistence: data/abuse_state.json (best-effort).
    Key: Telegram user_id (string in JSON).
    """

    def __init__(self) -> None:
        self._state: Dict[str, UserState] = {}
        self._load()

    def _load(self) -> None:
        try:
            if not STATE_FILE.exists():
                return
            raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return
            for k, v in raw.items():
                if not isinstance(v, dict):
                    continue
                self._state[str(k)] = UserState(
                    last_msg_ts=int(v.get("last_msg_ts", 0)),
                    spam_hits=int(v.get("spam_hits", 0)),
                    violations=int(v.get("violations", 0)),
                    cooldown_until=int(v.get("cooldown_until", 0)),
                    ban_until=int(v.get("ban_until", 0)),
                    ban_level=int(v.get("ban_level", 0)),
                    last_notice_ts=int(v.get("last_notice_ts", 0)),
                )
        except Exception:
            self._state = {}

    def _save(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            out = {}
            for k, s in self._state.items():
                out[k] = {
                    "last_msg_ts": s.last_msg_ts,
                    "spam_hits": s.spam_hits,
                    "violations": s.violations,
                    "cooldown_until": s.cooldown_until,
                    "ban_until": s.ban_until,
                    "ban_level": s.ban_level,
                    "last_notice_ts": s.last_notice_ts,
                }
            tmp = STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(STATE_FILE)
        except Exception:
            pass

    def _get(self, user_id: int) -> UserState:
        k = str(user_id)
        s = self._state.get(k)
        if not s:
            s = UserState()
            self._state[k] = s
        return s

    def _set_notice(self, user_id: int, ts: int) -> None:
        s = self._get(user_id)
        s.last_notice_ts = ts

    def should_notice(self, user_id: int) -> bool:
        s = self._get(user_id)
        now = _now()
        return (now - s.last_notice_ts) >= NOTICE_COOLDOWN_SEC

    def status(self, user_id: int) -> Tuple[str, int]:
        """
        Returns (status, seconds_left)
        status: "ok" | "cooldown" | "ban"
        """
        now = _now()
        s = self._get(user_id)

        if s.ban_until > now:
            return "ban", s.ban_until - now
        if s.cooldown_until > now:
            return "cooldown", s.cooldown_until - now
        return "ok", 0

    def on_message(self, user_id: int) -> Tuple[str, int]:
        """
        Call this on every user message.
        Applies the requested policy:

        - If user messages every 2 seconds or faster:
          after 3 spam hits -> cooldown 15 sec (violation +1).
        - If violations reach 5 -> ban 1 hour.
        - If user "breaks" the hour ban (sends messages during it) -> ban 1 day.

        Returns (status, seconds_left) after processing the message.
        """
        now = _now()
        s = self._get(user_id)

        # If banned and user still writes -> escalate to day ban
        if s.ban_until > now:
            if s.ban_level < 2:
                s.ban_level = 2
                s.ban_until = now + DAY_BAN_SEC
                s.cooldown_until = 0
                s.spam_hits = 0
                self._save()
            return "ban", s.ban_until - now

        # If in cooldown and user writes -> count as a violation (breaking cooldown)
        if s.cooldown_until > now:
            s.violations += 1
            # If violations reach threshold -> hour ban
            if s.violations >= VIOLATIONS_TO_HOUR_BAN:
                s.ban_level = 1
                s.ban_until = now + HOUR_BAN_SEC
                s.cooldown_until = 0
                s.spam_hits = 0
                self._save()
                return "ban", s.ban_until - now

            # keep cooldown, just return remaining
            s.last_msg_ts = now
            self._save()
            return "cooldown", s.cooldown_until - now

        # Not blocked: detect spam by interval
        if s.last_msg_ts:
            delta = now - s.last_msg_ts
            if delta <= SPAM_INTERVAL_SEC:
                s.spam_hits += 1
            else:
                s.spam_hits = 0
        else:
            s.spam_hits = 0

        s.last_msg_ts = now

        # After 3 spam hits -> cooldown 15 sec, violation +1
        if s.spam_hits >= SPAM_HITS_TO_COOLDOWN:
            s.spam_hits = 0
            s.cooldown_until = now + COOLDOWN_SEC
            s.violations += 1

            # After 5 violations -> 1 hour ban
            if s.violations >= VIOLATIONS_TO_HOUR_BAN:
                s.ban_level = 1
                s.ban_until = now + HOUR_BAN_SEC
                s.cooldown_until = 0
                self._save()
                return "ban", s.ban_until - now

            self._save()
            return "cooldown", COOLDOWN_SEC

        self._save()
        return "ok", 0
