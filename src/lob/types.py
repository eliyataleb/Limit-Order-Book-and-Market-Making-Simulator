from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Side(str, Enum):
    BID = "BID"
    ASK = "ASK"

    @property
    def opposite(self) -> "Side":
        return Side.ASK if self is Side.BID else Side.BID


class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


@dataclass(slots=True)
class Order:
    order_id: str
    timestamp: float
    side: Side
    order_type: OrderType
    qty: int
    price: Optional[float] = None
    owner: str = "FLOW"

    def __post_init__(self) -> None:
        if self.qty <= 0:
            raise ValueError("qty must be positive")
        if self.order_type is OrderType.LIMIT and self.price is None:
            raise ValueError("limit orders require a price")


@dataclass(slots=True, frozen=True)
class Trade:
    timestamp: float
    price: float
    qty: int
    taker_order_id: str
    maker_order_id: str
    taker_owner: str
    maker_owner: str
    taker_side: Side
