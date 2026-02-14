from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count

from .types import Order, OrderType, Side


@dataclass(slots=True)
class OrderFactory:
    prefix: str = "ORD"
    start: int = 1
    _counter: count = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._counter = count(self.start)

    def next_id(self) -> str:
        return f"{self.prefix}-{next(self._counter)}"

    def limit(self, timestamp: float, side: Side, price: float, qty: int, owner: str) -> Order:
        return Order(
            order_id=self.next_id(),
            timestamp=timestamp,
            side=side,
            order_type=OrderType.LIMIT,
            price=price,
            qty=qty,
            owner=owner,
        )

    def market(self, timestamp: float, side: Side, qty: int, owner: str) -> Order:
        return Order(
            order_id=self.next_id(),
            timestamp=timestamp,
            side=side,
            order_type=OrderType.MARKET,
            qty=qty,
            owner=owner,
        )
