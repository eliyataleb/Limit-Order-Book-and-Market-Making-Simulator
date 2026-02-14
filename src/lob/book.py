from __future__ import annotations

from bisect import bisect_left, insort
from collections import deque
from typing import Deque, Dict, Optional

from .types import Order, OrderType, Side, Trade


class LimitOrderBook:
    """FIFO limit order book with price-time priority and partial fills."""

    def __init__(self) -> None:
        self._bids: Dict[float, Deque[Order]] = {}
        self._asks: Dict[float, Deque[Order]] = {}
        self._bid_prices: list[float] = []  # ascending, best at the end
        self._ask_prices: list[float] = []  # ascending, best at the front
        self._order_index: dict[str, tuple[Side, float, Order]] = {}

    def best_bid(self) -> Optional[float]:
        return self._bid_prices[-1] if self._bid_prices else None

    def best_ask(self) -> Optional[float]:
        return self._ask_prices[0] if self._ask_prices else None

    def mid_price(self) -> Optional[float]:
        best_bid = self.best_bid()
        best_ask = self.best_ask()
        if best_bid is None or best_ask is None:
            return None
        return (best_bid + best_ask) / 2.0

    def spread(self) -> Optional[float]:
        best_bid = self.best_bid()
        best_ask = self.best_ask()
        if best_bid is None or best_ask is None:
            return None
        return best_ask - best_bid

    def top_depth(self) -> tuple[int, int]:
        bid_qty = 0
        ask_qty = 0
        best_bid = self.best_bid()
        best_ask = self.best_ask()
        if best_bid is not None:
            bid_qty = sum(order.qty for order in self._bids[best_bid])
        if best_ask is not None:
            ask_qty = sum(order.qty for order in self._asks[best_ask])
        return bid_qty, ask_qty

    def order_qty(self, order_id: str) -> Optional[int]:
        indexed = self._order_index.get(order_id)
        if indexed is None:
            return None
        return indexed[2].qty

    def open_orders(self, owner: Optional[str] = None) -> list[str]:
        if owner is None:
            return list(self._order_index.keys())
        return [oid for oid, (_, _, order) in self._order_index.items() if order.owner == owner]

    def add_order(self, order: Order) -> list[Trade]:
        trades: list[Trade] = []
        if order.order_type is OrderType.MARKET or self._is_marketable(order):
            trades.extend(self._match(order))

        if order.order_type is OrderType.LIMIT and order.qty > 0:
            self._add_resting(order)

        return trades

    def cancel(self, order_id: str) -> bool:
        indexed = self._order_index.get(order_id)
        if indexed is None:
            return False

        side, price, _ = indexed
        book = self._bids if side is Side.BID else self._asks
        queue = book.get(price)
        if queue is None:
            self._order_index.pop(order_id, None)
            return False

        removed = False
        for idx, resting in enumerate(queue):
            if resting.order_id == order_id:
                del queue[idx]
                removed = True
                break

        if not removed:
            self._order_index.pop(order_id, None)
            return False

        self._order_index.pop(order_id, None)

        if not queue:
            self._remove_price_level(side, price)

        return True

    def _is_marketable(self, order: Order) -> bool:
        if order.order_type is OrderType.MARKET:
            return True

        best_ask = self.best_ask()
        best_bid = self.best_bid()

        if order.side is Side.BID and best_ask is not None and order.price is not None:
            return order.price >= best_ask

        if order.side is Side.ASK and best_bid is not None and order.price is not None:
            return order.price <= best_bid

        return False

    def _match(self, taker: Order) -> list[Trade]:
        trades: list[Trade] = []

        while taker.qty > 0:
            best_price = self.best_ask() if taker.side is Side.BID else self.best_bid()
            if best_price is None:
                break

            if taker.order_type is OrderType.LIMIT and taker.price is not None:
                if taker.side is Side.BID and taker.price < best_price:
                    break
                if taker.side is Side.ASK and taker.price > best_price:
                    break

            maker_side = taker.side.opposite
            maker_book = self._asks if maker_side is Side.ASK else self._bids
            queue = maker_book[best_price]

            while queue and taker.qty > 0:
                maker = queue[0]
                fill_qty = min(taker.qty, maker.qty)
                maker.qty -= fill_qty
                taker.qty -= fill_qty

                trades.append(
                    Trade(
                        timestamp=taker.timestamp,
                        price=best_price,
                        qty=fill_qty,
                        taker_order_id=taker.order_id,
                        maker_order_id=maker.order_id,
                        taker_owner=taker.owner,
                        maker_owner=maker.owner,
                        taker_side=taker.side,
                    )
                )

                if maker.qty == 0:
                    queue.popleft()
                    self._order_index.pop(maker.order_id, None)

            if not queue:
                self._remove_price_level(maker_side, best_price)

        return trades

    def _add_resting(self, order: Order) -> None:
        if order.price is None:
            raise ValueError("resting order must have a price")

        book, price_levels = self._book_for_side(order.side)
        if order.price not in book:
            book[order.price] = deque()
            insort(price_levels, order.price)

        book[order.price].append(order)
        self._order_index[order.order_id] = (order.side, order.price, order)

    def _book_for_side(self, side: Side) -> tuple[dict[float, Deque[Order]], list[float]]:
        if side is Side.BID:
            return self._bids, self._bid_prices
        return self._asks, self._ask_prices

    def _remove_price_level(self, side: Side, price: float) -> None:
        book, levels = self._book_for_side(side)
        book.pop(price, None)
        idx = bisect_left(levels, price)
        if 0 <= idx < len(levels) and levels[idx] == price:
            levels.pop(idx)
