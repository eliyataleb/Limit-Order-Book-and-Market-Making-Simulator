from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _mid_at(timestamp: float, times: np.ndarray, mids: np.ndarray) -> float:
    return float(np.interp(timestamp, times, mids, left=mids[0], right=mids[-1]))


def build_metrics(raw: dict[str, Any], adverse_horizon: float) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    snapshots = pd.DataFrame(raw.get("snapshots", []))
    trades = pd.DataFrame(raw.get("trades", []))
    mm_fills = pd.DataFrame(raw.get("mm_fills", []))

    if snapshots.empty:
        raise ValueError("no snapshots captured")

    snapshots = snapshots.sort_values("timestamp").reset_index(drop=True)

    if not trades.empty:
        buy = trades.loc[trades["taker_side"] == "BID", "qty"].sum()
        sell = trades.loc[trades["taker_side"] == "ASK", "qty"].sum()
        denom = buy + sell
        flow_imbalance = float((buy - sell) / denom) if denom else 0.0
    else:
        flow_imbalance = 0.0

    summary: dict[str, float] = {
        "events": float(len(snapshots)),
        "trades": float(len(trades)),
        "flow_imbalance": flow_imbalance,
        "final_mid": float(snapshots["mid_price"].iloc[-1]),
        "final_fundamental": float(snapshots["fundamental_price"].iloc[-1]),
        "final_fundamental_gap": float(snapshots["fundamental_gap"].iloc[-1]),
        "final_inventory": float(snapshots["mm_inventory"].iloc[-1]),
        "final_realized_pnl": float(snapshots["mm_realized_pnl"].iloc[-1]),
        "final_unrealized_pnl": float(snapshots["mm_unrealized_pnl"].iloc[-1]),
        "final_pnl": float(snapshots["mm_pnl"].iloc[-1]),
        "final_mtm_pnl": float(snapshots["mm_mtm_pnl"].iloc[-1]),
        "avg_spread": float(snapshots["spread"].dropna().mean()) if snapshots["spread"].notna().any() else 0.0,
        "markout_horizon": float(adverse_horizon),
    }

    if mm_fills.empty:
        summary["mm_fills"] = 0.0
        summary["avg_markout"] = 0.0
        summary["avg_adverse_move"] = 0.0
        summary["adverse_fill_ratio"] = 0.0
        summary["adverse_selection_metric"] = 0.0
        return snapshots, trades, summary

    mm_fills = mm_fills.sort_values("timestamp").reset_index(drop=True)

    times = snapshots["timestamp"].to_numpy(dtype=float)
    mids = snapshots["mid_price"].to_numpy(dtype=float)

    markouts: list[float] = []
    adverse_moves: list[float] = []
    for fill in mm_fills.itertuples(index=False):
        mid_now = _mid_at(float(fill.timestamp), times, mids)
        future_mid = _mid_at(float(fill.timestamp) + adverse_horizon, times, mids)
        signed_markout = float(fill.mm_side) * (future_mid - mid_now)
        markouts.append(signed_markout)
        adverse_moves.append(-signed_markout)

    markout_arr = np.array(markouts, dtype=float)
    adverse_arr = np.array(adverse_moves, dtype=float)
    summary["mm_fills"] = float(len(mm_fills))
    summary["avg_markout"] = float(markout_arr.mean())
    summary["avg_adverse_move"] = float(adverse_arr.mean())
    summary["adverse_fill_ratio"] = float((markout_arr < 0).mean())
    summary["adverse_selection_metric"] = float(markout_arr.mean())

    return snapshots, trades, summary
