from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    LIMIT_ARRIVAL = "LIMIT_ARRIVAL"
    MARKET_ARRIVAL = "MARKET_ARRIVAL"
    CANCEL_ARRIVAL = "CANCEL_ARRIVAL"
    MM_QUOTE_UPDATE = "MM_QUOTE_UPDATE"
    TOXIC_MOVE = "TOXIC_MOVE"
    FUNDAMENTAL_MOVE = "FUNDAMENTAL_MOVE"


@dataclass(order=True, slots=True)
class Event:
    timestamp: float
    seq: int
    event_type: EventType = field(compare=False)
    payload: dict[str, Any] = field(default_factory=dict, compare=False)
