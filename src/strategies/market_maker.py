from __future__ import annotations

from dataclasses import dataclass, field

from lob.orders import OrderFactory
from lob.types import Order, Side, Trade


@dataclass(slots=True)
class MarketMakerConfig:
    half_spread_ticks: int = 1
    quote_qty: int = 3
    inventory_skew: float = 0.002


@dataclass(slots=True)
class MarketMaker:
    config: MarketMakerConfig
    tick_size: float
    inventory: int = 0
    cash: float = 0.0
    initial_cash: float = 0.0
    avg_entry_price: float = 0.0
    realized_pnl: float = 0.0
    active_order_ids: set[str] = field(default_factory=set)
    fills: list[dict] = field(default_factory=list)

    def make_quotes(
        self,
        timestamp: float,
        mid_price: float,
        best_bid: float | None,
        best_ask: float | None,
        factory: OrderFactory,
    ) -> list[Order]:
        half_spread = self.config.half_spread_ticks * self.tick_size
        skew = self.config.inventory_skew * self.inventory

        bid_price = self._round_to_tick(mid_price - half_spread - skew)
        ask_price = self._round_to_tick(mid_price + half_spread - skew)

        if best_ask is not None:
            bid_price = min(bid_price, self._round_to_tick(best_ask - self.tick_size))
        if best_bid is not None:
            ask_price = max(ask_price, self._round_to_tick(best_bid + self.tick_size))

        if bid_price >= ask_price:
            bid_price = self._round_to_tick(mid_price - self.tick_size)
            ask_price = self._round_to_tick(mid_price + self.tick_size)

        bid_order = factory.limit(timestamp, Side.BID, bid_price, self.config.quote_qty, owner="MM")
        ask_order = factory.limit(timestamp, Side.ASK, ask_price, self.config.quote_qty, owner="MM")
        return [bid_order, ask_order]

    def on_trade(self, trade: Trade) -> None:
        if trade.taker_owner == "MM":
            side = trade.taker_side
            self._apply_fill(side, trade.price, trade.qty)
        elif trade.maker_owner == "MM":
            side = trade.taker_side.opposite
            self._apply_fill(side, trade.price, trade.qty)
        else:
            return

    def total_pnl(self, mid_price: float) -> float:
        return self.realized_pnl + self.unrealized_pnl(mid_price)

    def unrealized_pnl(self, mid_price: float) -> float:
        if self.inventory == 0:
            return 0.0
        if self.inventory > 0:
            return (mid_price - self.avg_entry_price) * self.inventory
        return (self.avg_entry_price - mid_price) * abs(self.inventory)

    def mark_to_market(self, mid_price: float) -> float:
        return self.cash + self.inventory * mid_price - self.initial_cash

    def _apply_fill(self, side: Side, price: float, qty: int) -> None:
        trade_sign = 1 if side is Side.BID else -1
        cash_delta = -price * qty if side is Side.BID else price * qty

        self.cash += cash_delta
        self._update_position(trade_sign=trade_sign, qty=qty, price=price)
        self.fills.append(
            {
                "timestamp": None,
                "side": side.value,
                "mm_side": trade_sign,
                "price": price,
                "qty": qty,
            }
        )

    def _round_to_tick(self, value: float) -> float:
        return round(round(value / self.tick_size) * self.tick_size, 10)

    def _update_position(self, trade_sign: int, qty: int, price: float) -> None:
        if self.inventory == 0:
            self.inventory = trade_sign * qty
            self.avg_entry_price = price
            return

        if self.inventory * trade_sign > 0:
            current_abs = abs(self.inventory)
            new_abs = current_abs + qty
            self.avg_entry_price = ((self.avg_entry_price * current_abs) + (price * qty)) / new_abs
            self.inventory += trade_sign * qty
            return

        close_qty = min(abs(self.inventory), qty)
        if self.inventory > 0:
            self.realized_pnl += (price - self.avg_entry_price) * close_qty
        else:
            self.realized_pnl += (self.avg_entry_price - price) * close_qty

        self.inventory += trade_sign * close_qty
        remaining = qty - close_qty

        if self.inventory == 0:
            self.avg_entry_price = 0.0

        if remaining > 0:
            self.inventory = trade_sign * remaining
            self.avg_entry_price = price
