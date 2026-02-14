from __future__ import annotations

import heapq
from dataclasses import asdict, dataclass, field

import numpy as np

from lob import LimitOrderBook, OrderFactory, Side, Trade
from sim.arrivals import OrderFlowConfig, OrderFlowModel
from sim.events import Event, EventType
from strategies.market_maker import MarketMaker, MarketMakerConfig


@dataclass(slots=True)
class SimulatorConfig:
    seed: int = 7
    end_time: float = 300.0
    base_price: float = 100.0
    tick_size: float = 0.01
    mm_update_rate: float = 4.0
    mm_update_every_k_events: int = 1
    environment_mode: str = "v1_control"  # v1_control | v2_slow_adapt
    adverse_horizon: float = 1.0
    initial_depth_levels: int = 3
    initial_depth_qty: int = 20
    flow: OrderFlowConfig = field(default_factory=OrderFlowConfig)
    market_maker: MarketMakerConfig = field(default_factory=MarketMakerConfig)

    @classmethod
    def from_dict(cls, data: dict) -> "SimulatorConfig":
        flow = OrderFlowConfig(**data.get("flow", {}))
        mm = MarketMakerConfig(**data.get("market_maker", {}))
        kwargs = {k: v for k, v in data.items() if k not in {"flow", "market_maker"}}
        return cls(flow=flow, market_maker=mm, **kwargs)


class EventDrivenSimulator:
    def __init__(self, config: SimulatorConfig) -> None:
        self.config = config
        self.rng = np.random.default_rng(config.seed)

        self.book = LimitOrderBook()
        self.factory = OrderFactory(prefix="ORD")
        self.flow = OrderFlowModel(self.rng, config.flow)
        self.market_maker = MarketMaker(config.market_maker, tick_size=config.tick_size)

        self.now = 0.0
        self._seq = 0
        self._events: list[Event] = []
        self._event_count = 0
        self._last_mm_refresh_event = 0

        self.trades: list[Trade] = []
        self.snapshots: list[dict] = []
        self._last_mid = config.base_price
        self._fundamental_price = config.base_price

    def run(self) -> dict:
        self._seed_book()
        # MM starts with resting quotes; latency then controls refresh cadence.
        self._handle_mm_quote_update()
        self._schedule_initial_events()
        self._snapshot("INIT")

        while self._events:
            event = heapq.heappop(self._events)
            if event.timestamp > self.config.end_time:
                break

            self.now = event.timestamp
            self._event_count += 1
            snapshot_event = event.event_type.value
            mm_refreshed = False
            adapt_applied = False

            if event.event_type is EventType.LIMIT_ARRIVAL:
                self._handle_limit_arrival()
                self._schedule(EventType.LIMIT_ARRIVAL, self.flow.next_time(self.now, self.config.flow.limit_rate))

            elif event.event_type is EventType.MARKET_ARRIVAL:
                self._handle_market_arrival()
                self._schedule(EventType.MARKET_ARRIVAL, self.flow.next_time(self.now, self.config.flow.market_rate))

            elif event.event_type is EventType.CANCEL_ARRIVAL:
                self._handle_cancel_arrival()
                self._schedule(EventType.CANCEL_ARRIVAL, self.flow.next_time(self.now, self.config.flow.cancel_rate))

            elif event.event_type is EventType.FUNDAMENTAL_MOVE:
                self._handle_fundamental_move(event.payload)
                if event.payload.get("source") == "exogenous":
                    self._schedule_next_exogenous_fundamental_move()

            elif event.event_type is EventType.TOXIC_MOVE:
                # Backward compatibility for old saved event streams.
                self._handle_fundamental_move(event.payload)

            elif event.event_type is EventType.MM_QUOTE_UPDATE:
                # Optional legacy mode: rate-based quote refresh when K <= 0.
                if self.config.mm_update_every_k_events <= 0:
                    self._handle_mm_quote_update()
                    self._schedule(
                        EventType.MM_QUOTE_UPDATE,
                        self.flow.next_time(self.now, self.config.mm_update_rate),
                    )
                    mm_refreshed = True

            if self.config.mm_update_every_k_events > 0:
                k = max(1, self.config.mm_update_every_k_events)
                if self._event_count % k == 0:
                    self._handle_mm_quote_update()
                    mm_refreshed = True

            if self.config.environment_mode == "v2_slow_adapt":
                adapt_applied = self._apply_slow_fundamental_adaptation()

            if mm_refreshed:
                snapshot_event = f"{snapshot_event}|MM_REFRESH"
            if adapt_applied:
                snapshot_event = f"{snapshot_event}|FUND_ADAPT"
            self._snapshot(snapshot_event)

        return {
            "snapshots": self.snapshots,
            "trades": [
                {
                    "timestamp": trade.timestamp,
                    "price": trade.price,
                    "qty": trade.qty,
                    "taker_order_id": trade.taker_order_id,
                    "maker_order_id": trade.maker_order_id,
                    "taker_owner": trade.taker_owner,
                    "maker_owner": trade.maker_owner,
                    "taker_side": trade.taker_side.value,
                }
                for trade in self.trades
            ],
            "mm_fills": self.market_maker.fills,
            "config": asdict(self.config),
        }

    def _seed_book(self) -> None:
        base = self.config.base_price
        tick = self.config.tick_size

        for level in range(1, self.config.initial_depth_levels + 1):
            bid_price = round(base - level * tick, 10)
            ask_price = round(base + level * tick, 10)

            bid_order = self.factory.limit(
                timestamp=0.0,
                side=Side.BID,
                price=bid_price,
                qty=self.config.initial_depth_qty,
                owner="FLOW",
            )
            ask_order = self.factory.limit(
                timestamp=0.0,
                side=Side.ASK,
                price=ask_price,
                qty=self.config.initial_depth_qty,
                owner="FLOW",
            )

            self._process_trades(self.book.add_order(bid_order))
            self._process_trades(self.book.add_order(ask_order))

    def _schedule_initial_events(self) -> None:
        self._schedule(EventType.LIMIT_ARRIVAL, self.flow.next_time(0.0, self.config.flow.limit_rate))
        self._schedule(EventType.MARKET_ARRIVAL, self.flow.next_time(0.0, self.config.flow.market_rate))
        self._schedule(EventType.CANCEL_ARRIVAL, self.flow.next_time(0.0, self.config.flow.cancel_rate))

        if self.config.mm_update_every_k_events <= 0:
            self._schedule(EventType.MM_QUOTE_UPDATE, self.flow.next_time(0.0, self.config.mm_update_rate))

        self._schedule_next_exogenous_fundamental_move()

    def _schedule_next_exogenous_fundamental_move(self) -> None:
        t = self.flow.next_time(self.now, self.config.flow.fundamental_rate)
        if not np.isfinite(t):
            return

        payload = {
            "source": "exogenous",
            "signal": self.flow.sample_exogenous_signal(),
            "jump_ticks": max(1, int(self.config.flow.fundamental_jump_ticks)),
        }
        self._schedule(EventType.FUNDAMENTAL_MOVE, timestamp=t, payload=payload)

    def _schedule(self, event_type: EventType, timestamp: float, payload: dict | None = None) -> None:
        if not np.isfinite(timestamp):
            return
        heapq.heappush(
            self._events,
            Event(timestamp=timestamp, seq=self._seq, event_type=event_type, payload=payload or {}),
        )
        self._seq += 1

    def _handle_limit_arrival(self) -> None:
        mid = self.book.mid_price() or self._last_mid
        side, price, qty = self.flow.sample_limit(mid_price=mid, tick_size=self.config.tick_size)
        order = self.factory.limit(self.now, side=side, price=price, qty=qty, owner="FLOW")
        self._process_trades(self.book.add_order(order))

    def _handle_market_arrival(self) -> None:
        if self.flow.should_send_informed():
            side, qty, signal = self.flow.sample_informed_market()
            owner = "INFORMED"
            delay = max(0.0, float(self.config.flow.toxic_move_delay))
            self._schedule(
                EventType.FUNDAMENTAL_MOVE,
                timestamp=self.now + delay,
                payload={
                    "source": "informed",
                    "signal": int(signal),
                    "jump_ticks": max(1, int(self.config.flow.toxic_jump_ticks)),
                },
            )
        else:
            side, qty = self.flow.sample_market()
            owner = "FLOW"

        order = self.factory.market(self.now, side=side, qty=qty, owner=owner)
        self._process_trades(self.book.add_order(order))

    def _handle_cancel_arrival(self) -> None:
        candidates = self.book.open_orders(owner="FLOW")
        if not candidates:
            return
        cancel_id = str(self.rng.choice(candidates))
        self.book.cancel(cancel_id)

    def _handle_mm_quote_update(self) -> None:
        for order_id in list(self.market_maker.active_order_ids):
            self.book.cancel(order_id)
        self.market_maker.active_order_ids.clear()

        mid = self.book.mid_price() or self._last_mid
        quotes = self.market_maker.make_quotes(
            timestamp=self.now,
            mid_price=mid,
            best_bid=self.book.best_bid(),
            best_ask=self.book.best_ask(),
            factory=self.factory,
        )

        for quote in quotes:
            trades = self.book.add_order(quote)
            self._process_trades(trades)
            if quote.qty > 0:
                self.market_maker.active_order_ids.add(quote.order_id)

        self._last_mm_refresh_event = self._event_count

    def _handle_fundamental_move(self, payload: dict) -> None:
        signal = int(payload.get("signal", self.flow.sample_exogenous_signal()))
        signal = 1 if signal >= 0 else -1
        jump_ticks = max(1, int(payload.get("jump_ticks", self.config.flow.fundamental_jump_ticks)))
        source = str(payload.get("source", "unknown"))

        self._fundamental_price = round(
            self._fundamental_price + signal * jump_ticks * self.config.tick_size,
            10,
        )

        # v1 applies immediate impact after the latent signal (predictive informed flow).
        if self.config.environment_mode == "v1_control":
            self._apply_immediate_fundamental_impact(signal=signal, jump_ticks=jump_ticks, source=source)

    def _apply_immediate_fundamental_impact(self, signal: int, jump_ticks: int, source: str) -> None:
        base_qty = self._qty_to_force_jump(signal=signal, jump_ticks=jump_ticks)
        if base_qty <= 0:
            return

        impact = float(np.clip(self.config.flow.toxic_impact_fraction, 0.0, 1.0))
        if impact <= 0:
            return

        qty = max(1, int(round(base_qty * impact)))
        qty = min(base_qty, qty)

        side = Side.BID if signal > 0 else Side.ASK
        owner = "LATENT_MOVE" if source == "informed" else "FUNDAMENTAL_IMPACT"
        order = self.factory.market(self.now, side=side, qty=qty, owner=owner)
        self._process_trades(self.book.add_order(order))

    def _apply_slow_fundamental_adaptation(self) -> bool:
        mid = self.book.mid_price() or self._last_mid
        gap = self._fundamental_price - mid
        if abs(gap) < self.config.tick_size:
            return False

        if self.rng.random() >= float(np.clip(self.config.flow.slow_adapt_prob, 0.0, 1.0)):
            return False

        signal = 1 if gap > 0 else -1
        side = Side.BID if signal > 0 else Side.ASK
        one_tick_qty = self._qty_to_force_jump(signal=signal, jump_ticks=1)
        if one_tick_qty <= 0:
            return False

        gap_ticks = max(1, int(abs(gap) / self.config.tick_size))
        qty_cap = max(1, int(self.config.flow.slow_adapt_max_qty)) * min(5, gap_ticks)
        qty = max(1, min(one_tick_qty, qty_cap))

        order = self.factory.market(self.now, side=side, qty=qty, owner="FUND_ADAPT")
        self._process_trades(self.book.add_order(order))
        return True

    def _qty_to_force_jump(self, signal: int, jump_ticks: int) -> int:
        tick = self.config.tick_size

        if signal > 0:
            best_ask = self.book.best_ask()
            if best_ask is None:
                return 0
            target = round(best_ask + jump_ticks * tick, 10)
            qty = 0
            for price in self.book._ask_prices:
                if price < target:
                    qty += sum(order.qty for order in self.book._asks[price])
                else:
                    break
            return qty

        best_bid = self.book.best_bid()
        if best_bid is None:
            return 0
        target = round(best_bid - jump_ticks * tick, 10)
        qty = 0
        for price in reversed(self.book._bid_prices):
            if price > target:
                qty += sum(order.qty for order in self.book._bids[price])
            else:
                break
        return qty

    def _process_trades(self, trades: list[Trade]) -> None:
        if not trades:
            return

        self.trades.extend(trades)
        for trade in trades:
            pre_fill_count = len(self.market_maker.fills)
            self.market_maker.on_trade(trade)
            if len(self.market_maker.fills) > pre_fill_count:
                self.market_maker.fills[-1]["timestamp"] = trade.timestamp

    def _snapshot(self, event_type: str) -> None:
        best_bid = self.book.best_bid()
        best_ask = self.book.best_ask()
        mid = self.book.mid_price()
        if mid is not None:
            self._last_mid = mid
        else:
            mid = self._last_mid

        spread = self.book.spread()
        bid_depth, ask_depth = self.book.top_depth()
        unrealized = self.market_maker.unrealized_pnl(mid)

        self.snapshots.append(
            {
                "timestamp": self.now,
                "event_type": event_type,
                "event_idx": self._event_count,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "mid_price": mid,
                "fundamental_price": self._fundamental_price,
                "fundamental_gap": self._fundamental_price - mid,
                "spread": spread,
                "top_bid_depth": bid_depth,
                "top_ask_depth": ask_depth,
                "mm_inventory": self.market_maker.inventory,
                "mm_cash": self.market_maker.cash,
                "mm_realized_pnl": self.market_maker.realized_pnl,
                "mm_unrealized_pnl": unrealized,
                "mm_pnl": self.market_maker.total_pnl(mid),
                "mm_mtm_pnl": self.market_maker.mark_to_market(mid),
                "events_since_mm_refresh": self._event_count - self._last_mm_refresh_event,
            }
        )
