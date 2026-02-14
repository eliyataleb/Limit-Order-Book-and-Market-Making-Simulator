from __future__ import annotations

from .book import LimitOrderBook
from .types import Order, Trade


def submit_order(book: LimitOrderBook, order: Order) -> list[Trade]:
    return book.add_order(order)
