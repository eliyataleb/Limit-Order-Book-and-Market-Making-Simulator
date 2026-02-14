from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def save_plots(metrics: pd.DataFrame, output_dir: str | Path) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True)

    axes[0].plot(metrics["timestamp"], metrics["mid_price"], label="Mid", linewidth=1.6)
    axes[0].plot(metrics["timestamp"], metrics["best_bid"], label="Best Bid", alpha=0.6)
    axes[0].plot(metrics["timestamp"], metrics["best_ask"], label="Best Ask", alpha=0.6)
    axes[0].set_ylabel("Price")
    axes[0].set_title("Top of Book")
    axes[0].legend(loc="upper left")

    axes[1].plot(metrics["timestamp"], metrics["mm_inventory"], color="tab:orange", linewidth=1.4)
    axes[1].axhline(0.0, color="black", linewidth=0.8, alpha=0.5)
    axes[1].set_ylabel("Inventory")
    axes[1].set_title("Market Maker Inventory")

    axes[2].plot(metrics["timestamp"], metrics["mm_pnl"], color="tab:green", linewidth=1.4)
    axes[2].set_ylabel("PnL")
    axes[2].set_xlabel("Simulation Time")
    axes[2].set_title("Market Maker PnL")

    fig.tight_layout()
    fig.savefig(out / "core_timeseries.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

    axes[0].plot(metrics["timestamp"], metrics["spread"], color="tab:red", linewidth=1.2)
    axes[0].set_ylabel("Spread")
    axes[0].set_title("Spread Dynamics")

    axes[1].plot(metrics["timestamp"], metrics["top_bid_depth"], label="Top Bid Depth", linewidth=1.1)
    axes[1].plot(metrics["timestamp"], metrics["top_ask_depth"], label="Top Ask Depth", linewidth=1.1)
    axes[1].set_ylabel("Depth")
    axes[1].set_xlabel("Simulation Time")
    axes[1].set_title("Top-Level Depth")
    axes[1].legend(loc="upper right")

    fig.tight_layout()
    fig.savefig(out / "spread_depth.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)

    axes[0].plot(
        metrics["timestamp"],
        metrics["mm_realized_pnl"],
        color="tab:blue",
        linewidth=1.3,
        label="Realized",
    )
    axes[0].set_ylabel("Realized")
    axes[0].set_title("PnL Decomposition")
    axes[0].legend(loc="upper left")

    axes[1].plot(metrics["timestamp"], metrics["mm_unrealized_pnl"], color="tab:orange", linewidth=1.3, label="Unrealized")
    axes[1].set_ylabel("Unrealized")
    axes[1].legend(loc="upper left")

    axes[2].plot(metrics["timestamp"], metrics["mm_pnl"], color="tab:green", linewidth=1.4, label="Total PnL")
    axes[2].plot(metrics["timestamp"], metrics["mm_mtm_pnl"], color="tab:purple", linewidth=1.2, alpha=0.7, label="Cash+Inventory MTM")
    axes[2].set_ylabel("Total")
    axes[2].set_xlabel("Simulation Time")
    axes[2].legend(loc="upper left")

    fig.tight_layout()
    fig.savefig(out / "pnl_decomposition.png", dpi=150)
    plt.close(fig)
