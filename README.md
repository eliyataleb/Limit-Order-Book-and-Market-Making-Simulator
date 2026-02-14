# Event-Driven Limit Order Book + Market Maker Simulator

This project simulates exchange microstructure using a discrete-event engine and a FIFO limit order book. Instead of bar-level backtesting assumptions, it models individual limit/market/cancel events, queue priority, partial fills, and inventory-aware market making.

## What It Models

- Price-time priority (FIFO) at each level
- Limit orders, market orders, and cancellations
- Marketable limit order behavior and remainder resting
- Top-of-book dynamics (best bid/ask, spread, mid)
- Stochastic order flow with imbalance/informed-flow controls
- Market-maker latency via quote refresh every `K` events
- Predictive informed flow via latent signal + delayed fundamental move
- Optional v2 market-wide realism layer with slow adaptation to latent fundamental
- PnL decomposition (realized and unrealized) and adverse-selection diagnostics

## Repository Layout

```text
lob_sim/
  README.md
  requirements.txt
  configs/
    base.yaml
  src/
    lob/
    sim/
    strategies/
    analytics/
  scripts/
    run_sim.py
    run_experiments.py
  verification_tests/
  outputs/
```

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q verification_tests
python scripts/run_sim.py --config configs/base.yaml --output-dir outputs/base
python scripts/run_experiments.py --config configs/base.yaml --output-dir outputs/experiments
```

## Outputs

`run_sim.py` writes:

- `metrics.csv` (event-by-event state metrics)
- `trades.csv` (executed trades)
- `mm_fills.csv` (market-maker fill log)
- `summary.json` (headline diagnostics)
- `core_timeseries.png`, `spread_depth.png`, `pnl_decomposition.png`

`run_experiments.py` runs:

- `v1_control` bundle (control/calibration)
- `v2_realism` bundle (slow-adaptation environment)

Each bundle contains:

- `A_baseline` (with `latency_test.csv/.png`)
- `B_buy_imbalance`
- `C_informed_flow` (with `toxicity_sweep.csv/.png`)

Top-level comparison artifacts:

- `outputs/experiments/v1_vs_v2_compare.csv`
- `outputs/experiments/v1_vs_v2_latency.csv`
- `outputs/experiments/v1_vs_v2_toxicity.csv`

Signed markout convention: `avg_markout < 0` means adverse selection against the market maker.
