# Post-Mortem: Market Making Simulator & Microstructure Experiments

## Overview

This project is a systematic exploration of **market microstructure** through the construction of an **event-driven limit order book (LOB) simulator** and a sequence of controlled market-making experiments.

Rather than focusing on alpha generation or strategy optimization, the objective was to understand **how prices are formed at the microstructural level**, how liquidity is supplied and consumed through the limit order book, and under what conditions market makers earn or lose money.

The simulator models:
- The arrival of market and limit orders
- Price formation through best bid / best ask dynamics
- Queue priority (FIFO) at the top of book
- Inventory and cash accounting for a liquidity provider
- The interaction between order flow and subsequent price movements

By progressively introducing **order-flow imbalance**, **inventory pressure**, and finally **informational asymmetry**, the project isolates the mechanisms that turn the LOB from a benign spread-capture environment into a hostile, adverse-selection-dominated market.

A central theme of the project is that **information is not embedded directly in prices**, but instead emerges through **order flow interacting with the limit order book**. The experiments demonstrate how identical price processes can produce radically different outcomes for a market maker depending on whether trades are informationally neutral or predictive.

The final result is a microstructure-consistent simulation that reproduces:
- Spread capture in noise-dominated markets
- Inventory risk under imbalanced flow
- Systematic losses under informed trading

This project serves as a conceptual and empirical bridge between textbook LOB theory and the real-world constraints faced by market makers.

---

## Initial Design & Assumptions

### Market Model
- Mid-price generated as a synthetic stochastic process (random walk / diffusion)
- Top-of-book order book with bid/ask quotes
- Single market maker providing liquidity on both sides
- External agents submitting market orders

### Market Maker Logic
- Quotes around mid price with adjustable spread
- Inventory tracking
- Cash and mark-to-market PnL accounting
- Inventory-aware quote skewing

### Key Simplifying Assumption
At the start, **all order flow was informationally neutral**:
- No trader had predictive information
- Order flow was symmetric or randomly imbalanced
- Prices evolved independently of who traded

This assumption turned out to be the **core limitation** of early experiments.

---

## Experiment 1: Symmetric Noise Flow (Baseline)

### Setup
- Random buy/sell market orders
- No directional bias
- No informed traders
- Market maker updates quotes immediately

### Results
- Inventory mean-reverted around zero
- PnL trended steadily upward
- Unrealized PnL remained small
- Spread capture dominated returns

### Interpretation
This experiment validated that:
- The accounting logic was correct
- Spread capture alone can generate profits
- Inventory risk is manageable under symmetric flow

**This is the idealized textbook market-making regime.**

---

## Experiment 2: Order Flow Imbalance

### Motivation
In real markets, order flow is often imbalanced (more buyers than sellers or vice versa), even without information.

### Setup
- Introduced persistent buy/sell imbalance
- No predictive information about future prices
- Market maker allowed to:
  - Widen spread
  - Skew quotes
  - Manage inventory

### Results
- Inventory drifted but remained bounded
- PnL remained positive
- Spread widened dynamically
- No systematic adverse price movement after fills

### Interpretation
**Order flow imbalance alone is not toxic.**

A market maker can remain profitable if:
- Imbalance is not predictive
- Quotes adapt fast enough
- Inventory risk is controlled

This explains why real market makers can operate profitably during:
- Strong buying pressure
- Strong selling pressure
- Trend-like conditions

---

## First Major Red Flag

At this point:
- The market maker was profitable in *all* regimes
- Even when “informed traders” were introduced
- PnL still trended upward

This indicated a **structural flaw**, not a strategy success.

---

## Root Cause Analysis

The problem was **not** the strategy.

The problem was the definition of *informed flow*.

Previously:
- “Informed traders” were labeled but **not informationally different**
- They traded randomly like everyone else
- Prices evolved independently of their trades

This meant:
> There was no adverse selection, because no one had information.

---

## Experiment 3 (v1): Naive Informed Traders (Failed)

### Setup
- Introduced traders labeled as “informed”
- Higher aggressiveness
- Same random price process

### Results
- Market maker still profitable
- Markouts near zero
- No correlation between fills and future price moves

### Conclusion
Labeling traders as “informed” without **predictive conditioning** is meaningless.

---

## Key Conceptual Breakthrough

**Informed trading does not require deterministic prices.**

It requires:

$$
\mathbb{E}\left[\Delta P_{t+1} \mid \text{trade direction}\right] \neq 0
$$

In other words:
- Prices can remain random
- But order flow must be conditionally predictive

This insight led to the redesign of Experiment 3.

---

## Experiment 3 (v2): Predictive Informed Flow (Final)

### Design Changes
- Introduced a latent short-horizon signal
- Signal correlated with *future* price drift
- Informed traders:
  - Buy when signal > threshold
  - Sell when signal < −threshold
- Market maker does **not** observe the signal

### Toxicity Sweep
- Varied probability of informed participation (`p_informed`)
- Measured:
  - Final PnL
  - Average markout
  - Average adverse move
  - Adverse fill ratio

### Results
- Final PnL becomes negative as `p_informed` increases
- Losses accelerate non-linearly
- Average markout turns negative
- Adverse moves increase monotonically

### Interpretation
This experiment successfully reproduces:
- Adverse selection
- Toxic order flow
- Structural market-making losses

**This is the regime where real market makers lose money.**

---

## Final Conclusions

### 1. Spread Capture Is Not Alpha
Market makers earn spread only when:
- Order flow is not predictive
- Quotes are not systematically picked off

### 2. Imbalance ≠ Information
Markets can be heavily one-sided and still be non-toxic.

### 3. Adverse Selection Is the Core Risk
Losses arise when:
- Trades reveal information
- Prices move *after* fills
- Market makers are forced to trade at stale quotes

### 4. Information Lives in Order Flow, Not Prices
Prices may look random, but order flow is structured.

### 5. Latency and Information Asymmetry Matter
Fast adaptation alone cannot overcome informed flow if information arrives faster than quotes update.

---



