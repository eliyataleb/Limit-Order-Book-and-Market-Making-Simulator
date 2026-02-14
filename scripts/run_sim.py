from __future__ import annotations

import argparse
import json
from pathlib import Path
import os
import sys

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
MPL_DIR = ROOT / ".mplconfig"
MPL_DIR.mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_DIR))

from analytics import build_metrics, save_plots
from sim import EventDrivenSimulator, SimulatorConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a single event-driven LOB simulation.")
    parser.add_argument("--config", type=str, default="configs/base.yaml", help="Path to YAML config")
    parser.add_argument("--output-dir", type=str, default="outputs/base", help="Output directory")
    parser.add_argument("--seed", type=int, default=None, help="Optional seed override")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f) or {}

    if args.seed is not None:
        config_data["seed"] = int(args.seed)

    config = SimulatorConfig.from_dict(config_data)
    sim = EventDrivenSimulator(config)
    raw = sim.run()

    metrics, trades, summary = build_metrics(raw, adverse_horizon=config.adverse_horizon)

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    metrics.to_csv(out / "metrics.csv", index=False)
    trades.to_csv(out / "trades.csv", index=False)
    pd.DataFrame(raw.get("mm_fills", [])).to_csv(out / "mm_fills.csv", index=False)
    with open(out / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    save_plots(metrics, out)

    print(f"Saved outputs to {out.resolve()}")
    print(
        "Final summary: "
        f"trades={int(summary['trades'])}, "
        f"final_pnl={summary['final_pnl']:.4f}, "
        f"realized={summary['final_realized_pnl']:.4f}, "
        f"unrealized={summary['final_unrealized_pnl']:.4f}, "
        f"final_inventory={summary['final_inventory']:.0f}, "
        f"avg_markout={summary['avg_markout']:.6f}, "
        f"avg_adverse_move={summary['avg_adverse_move']:.6f}, "
        f"adverse_fill_ratio={summary['adverse_fill_ratio']:.2%}"
    )


if __name__ == "__main__":
    main()
