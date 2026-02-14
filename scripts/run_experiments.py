from __future__ import annotations

import argparse
import copy
import json
import shutil
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
MPL_DIR = ROOT / ".mplconfig"
MPL_DIR.mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_DIR))

import matplotlib.pyplot as plt
import pandas as pd
import yaml

from analytics import build_metrics, save_plots
from sim import EventDrivenSimulator, SimulatorConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run layered experiments: v1 controls then v2 realism.")
    parser.add_argument("--config", type=str, default="configs/base.yaml", help="Base YAML config")
    parser.add_argument("--output-dir", type=str, default="outputs/experiments", help="Output directory")
    parser.add_argument("--latency-values", type=str, default="1,5,10,20", help="Comma-separated K values")
    parser.add_argument(
        "--toxicity-values",
        type=str,
        default="0.0,0.1,0.3,0.6",
        help="Comma-separated p_informed values for informed-flow sweep",
    )
    parser.add_argument(
        "--informed-default-p",
        type=float,
        default=0.3,
        help="Default p_informed used for main C_informed_flow run",
    )
    parser.add_argument("--v2-fundamental-rate", type=float, default=3.0, help="Exogenous fundamental move rate in v2")
    parser.add_argument("--v2-fundamental-jump", type=int, default=1, help="Fundamental jump size (ticks) in v2")
    parser.add_argument("--v2-slow-adapt-prob", type=float, default=0.45, help="Slow-adaptation probability in v2")
    parser.add_argument("--v2-slow-adapt-max-qty", type=int, default=4, help="Max adaptation qty step in v2")
    return parser.parse_args()


def _parse_int_list(raw: str) -> list[int]:
    values = [int(x.strip()) for x in raw.split(",") if x.strip()]
    return [v for v in values if v > 0]


def _parse_float_list(raw: str) -> list[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def _deep_update(base: dict, updates: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_update(result[key], value)
        else:
            result[key] = value
    return result


def _run_case(name: str, config_data: dict, output_dir: Path) -> dict:
    config = SimulatorConfig.from_dict(config_data)
    raw = EventDrivenSimulator(config).run()
    metrics, trades, summary = build_metrics(raw, adverse_horizon=config.adverse_horizon)

    output_dir.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(output_dir / "metrics.csv", index=False)
    trades.to_csv(output_dir / "trades.csv", index=False)
    pd.DataFrame(raw.get("mm_fills", [])).to_csv(output_dir / "mm_fills.csv", index=False)
    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    save_plots(metrics, output_dir)

    summary["experiment"] = name
    summary["mm_update_every_k_events"] = float(config.mm_update_every_k_events)
    summary["p_informed"] = float(config.flow.p_informed)
    summary["imbalance"] = float(config.flow.imbalance)
    summary["environment_mode"] = config.environment_mode
    return summary


def _simulate_summary(config_data: dict) -> dict:
    config = SimulatorConfig.from_dict(config_data)
    raw = EventDrivenSimulator(config).run()
    _, _, summary = build_metrics(raw, adverse_horizon=config.adverse_horizon)
    return summary


def _plot_latency_test(df: pd.DataFrame, output_dir: Path, title_prefix: str) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(9, 7), sharex=True)

    axes[0].plot(df["k"], df["avg_markout"], marker="o", label="Avg Markout")
    axes[0].plot(df["k"], -df["avg_adverse_move"], marker="s", label="-Avg Adverse Move")
    axes[0].set_ylabel("Signed Value")
    axes[0].set_title(f"{title_prefix} Latency Test")
    axes[0].legend(loc="best")

    axes[1].plot(df["k"], df["final_pnl"], marker="o", label="Final PnL")
    axes[1].plot(df["k"], df["adverse_fill_ratio"], marker="s", label="Adverse Fill Ratio")
    axes[1].set_xlabel("MM Update Every K Events")
    axes[1].set_ylabel("Value")
    axes[1].legend(loc="best")

    fig.tight_layout()
    fig.savefig(output_dir / "latency_test.png", dpi=150)
    plt.close(fig)


def _plot_toxic_sweep(df: pd.DataFrame, output_dir: Path, title_prefix: str) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(9, 7), sharex=True)

    axes[0].plot(df["p_informed"], df["avg_markout"], marker="o", label="Avg Markout")
    axes[0].plot(df["p_informed"], df["avg_adverse_move"], marker="s", label="Avg Adverse Move")
    axes[0].set_ylabel("Signed Value")
    axes[0].set_title(f"{title_prefix} Informed-Flow Toxicity Sweep")
    axes[0].legend(loc="best")

    axes[1].plot(df["p_informed"], df["final_pnl"], marker="o", label="Final PnL")
    axes[1].plot(df["p_informed"], df["adverse_fill_ratio"], marker="s", label="Adverse Fill Ratio")
    axes[1].set_xlabel("p_informed")
    axes[1].set_ylabel("Value")
    axes[1].legend(loc="best")

    fig.tight_layout()
    fig.savefig(output_dir / "toxicity_sweep.png", dpi=150)
    plt.close(fig)


def _clean_output(output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    for name in [
        "v1_control",
        "v2_realism",
        "A_baseline",
        "B_buy_imbalance",
        "C_informed_flow",
        "latency_sweep",
        "toxicity_sweep",
        "pnl_decomposition",
    ]:
        target = output_root / name
        if target.exists():
            shutil.rmtree(target)

    for csv_name in [
        "summary_table.csv",
        "v1_vs_v2_compare.csv",
        "v1_vs_v2_latency.csv",
        "v1_vs_v2_toxicity.csv",
    ]:
        path = output_root / csv_name
        if path.exists():
            path.unlink()


def _run_bundle(
    bundle_name: str,
    base_config: dict,
    output_root: Path,
    env_updates: dict,
    latency_values: list[int],
    toxicity_values: list[float],
    informed_default_p: float,
) -> dict[str, pd.DataFrame]:
    bundle_root = output_root / bundle_name
    bundle_root.mkdir(parents=True, exist_ok=True)

    scenario_defs = {
        "A_baseline": {
            "flow": {
                "imbalance": 0.0,
                "p_informed": 0.0,
            }
        },
        "B_buy_imbalance": {
            "flow": {
                "imbalance": 0.35,
                "p_informed": 0.0,
            }
        },
        "C_informed_flow": {
            "flow": {
                "imbalance": 0.0,
                "p_informed": float(informed_default_p),
            }
        },
    }

    scenario_summaries: list[dict] = []
    for name, scenario_updates in scenario_defs.items():
        cfg = _deep_update(base_config, env_updates)
        cfg = _deep_update(cfg, scenario_updates)
        summary = _run_case(name, cfg, bundle_root / name)
        scenario_summaries.append(summary)

    latency_rows: list[dict] = []
    for k in latency_values:
        cfg = _deep_update(base_config, env_updates)
        cfg = _deep_update(
            cfg,
            {
                "mm_update_every_k_events": int(k),
                "flow": {
                    "imbalance": 0.0,
                    "p_informed": 0.0,
                },
            },
        )
        summary = _simulate_summary(cfg)
        latency_rows.append(
            {
                "k": int(k),
                "final_pnl": summary["final_pnl"],
                "avg_markout": summary["avg_markout"],
                "avg_adverse_move": summary["avg_adverse_move"],
                "adverse_fill_ratio": summary["adverse_fill_ratio"],
            }
        )

    latency_df = pd.DataFrame(latency_rows).sort_values("k").reset_index(drop=True)
    latency_df.to_csv(bundle_root / "A_baseline" / "latency_test.csv", index=False)
    _plot_latency_test(latency_df, bundle_root / "A_baseline", title_prefix=bundle_name)

    toxicity_rows: list[dict] = []
    for p in toxicity_values:
        cfg = _deep_update(base_config, env_updates)
        cfg = _deep_update(
            cfg,
            {
                "flow": {
                    "imbalance": 0.0,
                    "p_informed": float(p),
                }
            },
        )
        summary = _simulate_summary(cfg)
        toxicity_rows.append(
            {
                "p_informed": float(p),
                "final_pnl": summary["final_pnl"],
                "avg_markout": summary["avg_markout"],
                "avg_adverse_move": summary["avg_adverse_move"],
                "adverse_fill_ratio": summary["adverse_fill_ratio"],
            }
        )

    toxicity_df = pd.DataFrame(toxicity_rows).sort_values("p_informed").reset_index(drop=True)
    toxicity_df.to_csv(bundle_root / "C_informed_flow" / "toxicity_sweep.csv", index=False)
    _plot_toxic_sweep(toxicity_df, bundle_root / "C_informed_flow", title_prefix=bundle_name)

    scenario_df = pd.DataFrame(scenario_summaries)
    scenario_df.to_csv(bundle_root / "summary_table.csv", index=False)

    return {
        "scenarios": scenario_df,
        "latency": latency_df,
        "toxicity": toxicity_df,
    }


def _build_v1_v2_comparison(v1: pd.DataFrame, v2: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "experiment",
        "final_pnl",
        "final_realized_pnl",
        "final_unrealized_pnl",
        "avg_markout",
        "avg_adverse_move",
        "adverse_fill_ratio",
    ]

    left = v1[cols].copy().rename(columns={c: f"{c}_v1" for c in cols if c != "experiment"})
    right = v2[cols].copy().rename(columns={c: f"{c}_v2" for c in cols if c != "experiment"})
    merged = left.merge(right, on="experiment", how="inner")

    for metric in [
        "final_pnl",
        "final_realized_pnl",
        "final_unrealized_pnl",
        "avg_markout",
        "avg_adverse_move",
        "adverse_fill_ratio",
    ]:
        merged[f"delta_{metric}"] = merged[f"{metric}_v2"] - merged[f"{metric}_v1"]

    return merged


def main() -> None:
    args = parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        base_config = yaml.safe_load(f) or {}

    output_root = Path(args.output_dir)
    _clean_output(output_root)

    latency_values = _parse_int_list(args.latency_values)
    toxicity_values = _parse_float_list(args.toxicity_values)
    if not latency_values:
        raise ValueError("latency_values must contain at least one positive integer")
    if not toxicity_values:
        raise ValueError("toxicity_values must contain at least one value")

    v1_updates = {
        "environment_mode": "v1_control",
        "flow": {
            "fundamental_rate": 0.0,
        },
    }

    v2_updates = {
        "environment_mode": "v2_slow_adapt",
        "flow": {
            "fundamental_rate": float(args.v2_fundamental_rate),
            "fundamental_jump_ticks": int(args.v2_fundamental_jump),
            "slow_adapt_prob": float(args.v2_slow_adapt_prob),
            "slow_adapt_max_qty": int(args.v2_slow_adapt_max_qty),
        },
    }

    v1 = _run_bundle(
        bundle_name="v1_control",
        base_config=base_config,
        output_root=output_root,
        env_updates=v1_updates,
        latency_values=latency_values,
        toxicity_values=toxicity_values,
        informed_default_p=args.informed_default_p,
    )

    v2 = _run_bundle(
        bundle_name="v2_realism",
        base_config=base_config,
        output_root=output_root,
        env_updates=v2_updates,
        latency_values=latency_values,
        toxicity_values=toxicity_values,
        informed_default_p=args.informed_default_p,
    )

    compare_df = _build_v1_v2_comparison(v1["scenarios"], v2["scenarios"])
    compare_df.to_csv(output_root / "v1_vs_v2_compare.csv", index=False)

    latency_compare = v1["latency"].merge(v2["latency"], on="k", suffixes=("_v1", "_v2"))
    latency_compare.to_csv(output_root / "v1_vs_v2_latency.csv", index=False)

    toxicity_compare = v1["toxicity"].merge(v2["toxicity"], on="p_informed", suffixes=("_v1", "_v2"))
    toxicity_compare.to_csv(output_root / "v1_vs_v2_toxicity.csv", index=False)

    view_cols = [
        "experiment",
        "final_pnl_v1",
        "final_pnl_v2",
        "delta_final_pnl",
        "avg_markout_v1",
        "avg_markout_v2",
        "delta_avg_markout",
    ]

    print("\nV1 control (main experiments)")
    print(v1["scenarios"][[
        "experiment",
        "final_pnl",
        "final_realized_pnl",
        "final_unrealized_pnl",
        "avg_markout",
        "avg_adverse_move",
        "adverse_fill_ratio",
    ]].to_string(index=False))

    print("\nV2 realism (main experiments)")
    print(v2["scenarios"][[
        "experiment",
        "final_pnl",
        "final_realized_pnl",
        "final_unrealized_pnl",
        "avg_markout",
        "avg_adverse_move",
        "adverse_fill_ratio",
    ]].to_string(index=False))

    print("\nV1 vs V2 (main deltas)")
    print(compare_df[view_cols].to_string(index=False))

    print(f"\nSaved layered experiment artifacts to {output_root.resolve()}")


if __name__ == "__main__":
    main()
