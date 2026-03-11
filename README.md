# APEX Scalper
### Adaptive Price EXecution — Multi-Asset Confluence Scalping Algorithm

---

## Overview

**APEX Scalper** is a production-grade, multi-asset scalping algorithm built on a **weighted confluence scoring system**. It combines four distinct edge types into a single ranked signal before committing any capital, ensuring only high-probability setups are traded.

**Data Source:** Oanda REST API  
**Execution:** MetaTrader 5 via Python bridge (Phase 2)  
**Primary Timeframe:** M5 (entry), M15 + H1 (bias/structure)  
**Instruments:** XAUUSD, SPX500, DAX (DE30), US30, NAS100  

---

## Strategy Architecture

```
┌─────────────────────────────────────────────────────────┐
│                LAYER 1 — REGIME FILTER                  │
│   Session Gate → ATR Gate → Spread Gate → ADX Regime    │
│   If ANY check fails → no signal evaluation → wait      │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│              LAYER 2 — HTF BIAS ENGINE                  │
│   M15 EMA Stack + H1 Structure + Daily VWAP             │
│   Establishes directional compass before M5 entry       │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│              LAYER 3 — SIGNAL ENGINE (4 Modules)        │
│                                                         │
│   Module A — Momentum         (EMA cross, RSI, MACD)    │
│   Module B — Mean Reversion   (VWAP dev, BB, RSI div)   │
│   Module C — Order Flow       (Volume proxy, pressure)  │
│   Module D — SMC/Liquidity    (Sweeps, OB, BOS)         │
│   Module E — HTF Bonus        (Alignment score)         │
│                                                         │
│   Max score: 10/10 | Min to trade: 5/10                 │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│              LAYER 4 — RISK & EXECUTION ENGINE          │
│   ATR SL sizing → Score-tiered lots → Tiered TP         │
│   Daily DD limit → Max open trades → Spread gate        │
└─────────────────────────────────────────────────────────┘
```

---

## Confluence Scoring System

| Module | Edge Type | Max Score |
|--------|-----------|-----------|
| A — Momentum | EMA 5×13 cross, RSI, MACD histogram | 2.0 pts |
| B — Mean Reversion | VWAP deviation, Bollinger Bands, RSI divergence | 2.0 pts |
| C — Order Flow | Volume proxy spike, bar pressure, price velocity | 2.0 pts |
| D — SMC / Liquidity | Liquidity sweep, Order Block rejection, BOS | 2.0 pts |
| E — HTF Alignment | M15 EMA stack + H1 structure alignment bonus | 2.0 pts |
| **TOTAL** | | **10.0 pts** |

**Minimum score to trade: 5/10**

### Score → Position Size Tiers

| Score Range | Size Multiplier | Effective Risk |
|-------------|-----------------|----------------|
| 5–6 | 0.5× | 0.25% per trade |
| 7–8 | 0.75× | 0.375% per trade |
| 9–10 | 1.0× | 0.50% per trade |

---

## Risk Management

| Parameter | Value                           |
|-----------|---------------------------------|
| Base Risk per Trade | 0.5% of account                 |
| Max Risk Hard Cap | 1.0%                            |
| Daily Drawdown Limit | -5% (algo halts for day)        |
| Max Open Trades (Total) | 5                               |
| Max Open Trades (Per Instrument) | 2                               |
| Stop Loss | 1.5× ATR from entry             |
| Take Profit 1 | 1:1 RR → close 40%              |
| Take Profit 2 | 1:2 RR → close 40%              |
| Take Profit 3 | 1:3 RR → trail final 20%        |
| Trailing Stop | 0.75× ATR (activates after TP1) |
| Spread Filter | Skip if > 1.5× typical spread   |

---

## Session Windows (UTC)

| Instrument | Active Session |
|------------|----------------|
| XAUUSD | 07:00 – 17:00 (London + NY overlap) |
| SPX500 / US30 / NAS100 | 13:30 – 20:00 (NYSE hours) |
| DE30 (DAX) | 07:00 – 15:30 (Xetra hours) |

---

## Project Structure

```
Algo-APEX_Scalper/
│
├── config/
│   ├── settings.py              # ✦ ALL configurable parameters (edit here)
│   └── instruments.py           # Per-asset specs (pip value, sessions, magic numbers)
│
├── src/
│   ├── data/
│   │   ├── oanda_client.py      # Oanda API connection + paginated candle fetching
│   │   └── market_data.py       # Multi-TF data manager + indicator computation
│   │
│   ├── filters/
│   │   ├── regime.py            # Session gate, ATR gate, ADX regime detection
│   │   └── htf_bias.py          # M15 EMA stack, H1 structure, VWAP bias
│   │
│   ├── signals/
│   │   ├── momentum.py          # Module A — EMA cross, RSI, MACD
│   │   ├── mean_reversion.py    # Module B — VWAP dev, BB, RSI divergence
│   │   ├── order_flow.py        # Module C — Volume proxy, bar pressure
│   │   ├── smc.py               # Module D — Liquidity sweeps, OB, BOS
│   │   └── scorer.py            # Confluence aggregator (0–10 score)
│   │
│   ├── risk/
│   │   ├── position_sizer.py    # ATR-based lot sizing with score tiers
│   │   └── risk_manager.py      # Daily DD, max trades, P&L tracking
│   │
│   ├── execution/               # [Phase 2] MT5 bridge — order routing
│   │
│   └── utils/
│       └── logger.py            # Windows-safe file + console logger (plain FileHandler)
│
├── scripts/                     # ✦ Pipeline — run each step independently
│   ├── __init__.py
│   ├── 01_collect_data.py       # Fetch Oanda → compute indicators → save parquets
│   ├── 02_run_backtest.py       # Load parquets → run engine → save results pickle
│   ├── 03_plot_results.py       # Load results → generate all PNG charts
│   └── 04_generate_report.py   # Load results → generate investor Excel report
│
├── backtests/
│   ├── engine.py                # Bar-by-bar backtest engine (anti-lookahead)
│   └── reports/                 # Generated Excel reports saved here
│
├── data/
│   ├── raw/                     # Parquet files: {INSTRUMENT}_{TIMEFRAME}.parquet
│   ├── results/                 # backtest_results.pkl (consumed by steps 3 & 4)
│   └── plots/                   # PNG chart outputs
│
├── logs/                        # Runtime logs (apex_scalper.log — overwritten per run)
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

---

## Setup & Installation

### 1. Create Directory Structure

Run from the project root in PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path scripts
New-Item -ItemType Directory -Force -Path data\raw
New-Item -ItemType Directory -Force -Path data\results
New-Item -ItemType Directory -Force -Path data\plots
New-Item -ItemType File     -Force -Path scripts\__init__.py
```

### 2. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure Credentials

Edit `config/settings.py`:

```python
OANDA_ACCOUNT_ID  = "YOUR_ACCOUNT_ID"
OANDA_API_KEY     = "YOUR_API_KEY"
OANDA_ENVIRONMENT = "practice"   # or "live"
```

### 4. Configure Backtest Parameters

Also in `config/settings.py`:

```python
BACKTEST_START  = "2024-01-01"
BACKTEST_END    = "2026-03-05"
INITIAL_CAPITAL = 10_000.0
```

---

## Running the Pipeline

Each step is independent. Run them in order. If a later step fails, fix and re-run only that step — no need to re-fetch data.

### Step 1 — Collect & Save Market Data
Fetches all instruments × timeframes from Oanda, computes all indicators,
and saves each as a Parquet file to `data/raw/`.

```powershell
python -m scripts.01_collect_data
```

Output: `data/raw/XAU_USD_M5.parquet`, `data/raw/XAU_USD_M15.parquet`, … (15 files total)

---

### Step 2 — Run Backtest
Loads parquets, runs the full bar-by-bar engine, and saves results.

```powershell
python -m scripts.02_run_backtest
```

Output: `data/results/backtest_results.pkl`

---

### Step 3 — Generate Charts
Produces four chart types saved as PNG files.

```powershell
python -m scripts.03_plot_results
```

Output files in `data/plots/`:

| File | Contents |
|------|----------|
| `{INSTRUMENT}_equity_dd.png` | Per-asset equity curve + drawdown (2-panel) |
| `combined_equity.png` | All instruments + portfolio on one chart |
| `portfolio_equity_dd.png` | Portfolio equity + drawdown (2-panel) |
| `all_in_one.png` | Full dashboard grid — all assets + portfolio |

---

### Step 4 — Generate Excel Report
Produces the investor-grade Excel workbook.

```powershell
python -m scripts.04_generate_report
```

Output: `backtests/reports/APEX_Scalper_Report_{start}_{end}_{timestamp}.xlsx`

---

## Excel Report Structure

| Sheet | Contents |
|-------|----------|
| 1. Summary Dashboard | Portfolio KPIs — returns, risk ratios, trade stats |
| 2. Instrument Performance | Side-by-side per-asset comparison table |
| 3. Monthly Returns (Portfolio) | Heatmap — rows: years, cols: months, colour-coded P&L |
| 4. Monthly Returns (Per Asset) | Same heatmap for each individual instrument |
| 5. Trade Log | Full trade-by-trade detail with entries, exits, partials, reasons |
| 6. Equity Data | Daily equity time-series per instrument + portfolio |

---

## Legacy Single-Run (Original Entry Point)

The original monolithic runner still works and uses the Oanda live-fetch path:

```powershell
python -m src.main
```

This is equivalent to Steps 1 + 2 combined in a single run. Recommended only for quick tests — use the pipeline scripts for all serious backtesting.

---

## Indicator Reference

| Indicator | Parameters | Purpose |
|-----------|-----------|---------|
| EMA | 5, 13, 20, 50, 200 | Trend direction, crossovers |
| RSI | 14 | Momentum confirmation, divergence |
| MACD | 12/26/9 | Histogram direction |
| ATR | 14 | Dynamic SL sizing, volatility gate |
| Bollinger Bands | 20, 2σ | Mean reversion extremes |
| ADX | 14 | Regime classification (trending vs ranging) |
| VWAP | Daily anchor | Price fairness reference, mean reversion target |

---

## Key Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| Modules A (momentum) and B (mean reversion) are directionally opposed | Scorer only counts the module whose direction aligns with final consensus vote |
| Regime-aware weighting | Trending regime boosts momentum + SMC; ranging regime boosts mean reversion + order flow |
| Volume proxy = bar range / ATR | True tick volume unreliable on Oanda CFD feeds |
| VWAP fallback to SMA20 | Prevents failure when tick volume is zero |
| Plain `FileHandler` (not `RotatingFileHandler`) | Avoids Windows `PermissionError` [WinError 32] on log rollover |
| Parquet format for data storage | ~50ms load time for 150k bars vs several seconds for CSV |
| Bar-by-bar anti-lookahead | At bar `i`, only `df.iloc[:i+1]` is visible to all signal modules |

---

## Development Phases

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | Backtest engine, signal stack, risk engine, pipeline scripts, reporting |
| Phase 2 | 🔲 Pending | MT5 execution bridge (order routing, SL/TP management) |
| Phase 3 | 🔲 Pending | Live trading loop (Oanda stream → signal → MT5 execute) |
| Phase 4 | 🔲 Pending | Telegram / Discord trade alerts |
| Phase 5 | 🔲 Pending | Walk-forward optimisation + Monte Carlo simulation |

---

*APEX Scalper — Built for precision. Designed for longevity.*
