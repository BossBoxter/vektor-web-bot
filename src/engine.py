from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .ui import PACKAGES

class State(str, Enum):
    IDLE = "IDLE"
    LEAD_TZ = "LEAD_TZ"
    LEAD_CONTACT = "LEAD_CONTACT"

@dataclass
class LeadContext:
    source: str = "consult"          # consult | order
    package_name: Optional[str] = None
    tz: Optional[str] = None
    contact: Optional[str] = None

def get_ctx(user_data: dict) -> LeadContext:
    raw = user_data.get("lead_ctx")
    if isinstance(raw, LeadContext):
        return raw
    ctx = LeadContext()
    user_data["lead_ctx"] = ctx
    return ctx

def set_state(user_data: dict, state: State):
    user_data["state"] = state.value

def get_state(user_data: dict) -> State:
    v = user_data.get("state")
    try:
        return State(v) if v else State.IDLE
    except Exception:
        return State.IDLE

def reset(user_data: dict):
    user_data.clear()

def start_consult(user_data: dict):
    reset(user_data)
    set_state(user_data, State.LEAD_TZ)
    ctx = get_ctx(user_data)
    ctx.source = "consult"
    ctx.package_name = None

def start_order(user_data: dict, package_name: str):
    reset(user_data)
    set_state(user_data, State.LEAD_TZ)
    ctx = get_ctx(user_data)
    ctx.source = "order"
    ctx.package_name = package_name if package_name in PACKAGES else None

def accept_tz(user_data: dict, tz: str):
    ctx = get_ctx(user_data)
    ctx.tz = tz
    set_state(user_data, State.LEAD_CONTACT)

def accept_contact(user_data: dict, contact: str):
    ctx = get_ctx(user_data)
    ctx.contact = contact
    set_state(user_data, State.IDLE)
