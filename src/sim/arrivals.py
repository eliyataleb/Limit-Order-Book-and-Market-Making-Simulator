from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lob.types import Side


@dataclass(slots=True)
class OrderFlowConfig:
    limit_rate: float = 25.0
    market_rate: float = 12.0
    cancel_rate: float = 8.0
    imbalance: float = 0.0
    limit_levels: int = 4
    limit_qty_min: int = 1
    limit_qty_max: int = 6
    market_qty_min: int = 1
    market_qty_max: int = 4
    marketable_limit_prob: float = 0.1
    # Legacy directional-bias control kept for compatibility with old configs.
    informed_market_bias: float = 0.0
    trend_flip_prob: float = 0.02
    # Predictive/toxic flow controls.
    p_informed: float = 0.0
    informed_qty_mult: float = 1.8
    signal_flip_prob: float = 0.02
    toxic_move_delay: float = 0.05
    toxic_jump_ticks: int = 1
    toxic_impact_fraction: float = 1.0
    # Exogenous latent fundamental process (disabled in v1 by default).
    fundamental_rate: float = 0.0
    fundamental_jump_ticks: int = 1
    # v2 slow-adaptation layer: market transitions toward fundamental over many events.
    slow_adapt_prob: float = 0.35
    slow_adapt_max_qty: int = 4


class OrderFlowModel:
    def __init__(self, rng: np.random.Generator, config: OrderFlowConfig) -> None:
        self.rng = rng
        self.config = config
        self._trend = 1 if self.rng.random() < 0.5 else -1
        self._signal = 1 if self.rng.random() < 0.5 else -1

    def next_time(self, current_time: float, rate: float) -> float:
        if rate <= 0:
            return float("inf")
        return current_time + float(self.rng.exponential(1.0 / rate))

    def sample_limit(self, mid_price: float, tick_size: float) -> tuple[Side, float, int]:
        side = self.sample_side(is_market=False)
        qty = self._sample_qty(self.config.limit_qty_min, self.config.limit_qty_max)

        passive_level = int(self.rng.integers(1, self.config.limit_levels + 1))
        if side is Side.BID:
            price = mid_price - passive_level * tick_size
            if self.rng.random() < self.config.marketable_limit_prob:
                price = mid_price + tick_size
        else:
            price = mid_price + passive_level * tick_size
            if self.rng.random() < self.config.marketable_limit_prob:
                price = mid_price - tick_size

        return side, self._round_to_tick(price, tick_size), qty

    def sample_market(self) -> tuple[Side, int]:
        side = self.sample_side(is_market=True)
        qty = self._sample_qty(self.config.market_qty_min, self.config.market_qty_max)
        return side, qty

    def should_send_informed(self) -> bool:
        p = float(np.clip(self.config.p_informed, 0.0, 1.0))
        return bool(self.rng.random() < p)

    def sample_informed_market(self) -> tuple[Side, int, int]:
        signal = self.sample_signal()
        side = Side.BID if signal > 0 else Side.ASK
        base_qty = self._sample_qty(self.config.market_qty_min, self.config.market_qty_max)
        qty = max(1, int(round(base_qty * self.config.informed_qty_mult)))
        return side, qty, signal

    def sample_signal(self) -> int:
        flip_prob = self.config.signal_flip_prob
        if self.rng.random() < flip_prob:
            self._signal *= -1
        return self._signal

    def sample_exogenous_signal(self) -> int:
        return 1 if self.rng.random() < 0.5 else -1

    def sample_side(self, is_market: bool) -> Side:
        imbalance = max(-1.0, min(1.0, self.config.imbalance))
        p_buy = 0.5 + 0.5 * imbalance

        if is_market and self.config.informed_market_bias > 0:
            if self.rng.random() < self.config.trend_flip_prob:
                self._trend *= -1
            p_buy += self.config.informed_market_bias * self._trend

        p_buy = float(np.clip(p_buy, 0.01, 0.99))
        return Side.BID if self.rng.random() < p_buy else Side.ASK

    def _sample_qty(self, low: int, high: int) -> int:
        return int(self.rng.integers(low, high + 1))

    @staticmethod
    def _round_to_tick(value: float, tick_size: float) -> float:
        return round(round(value / tick_size) * tick_size, 10)
