# apex_scalper/README.md

# APEX Scalper
### Adaptive Price EXecution — Multi-Asset Confluence Scalping Algorithm

---

## Overview

**APEX Scalper** is a production-grade, multi-asset scalping algorithm built on a **weighted confluence scoring system**. It combines four distinct edge types into a single ranked signal before committing any capital, ensuring only high-probability setups are traded.

**Data Source:** Oanda REST API  
**Execution:** MetaTrader 5 via Python bridge  
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
│   Module A — Momentum         (EMA cross, RSI, MACD)   │
│   Module B — Mean Reversion   (VWAP dev, BB, RSI div)  │
│   Module C — Order Flow       (Volume proxy, pressure) │
│   Module D — SMC/Liquidity    (Sweeps, OB, BOS)        │
│   Module E — HTF Bonus        (Alignment score)        │
│                                                         │
│   Max score: 10/10 | Min to trade: 5/10                │
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

| Parameter | Value |
|-----------|-------|
| Base Risk per Trade | 0.5% of account |
| Max Risk Hard Cap | 1.0% |
| Daily Drawdown Limit | -2% (algo halts for day) |
| Max Open Trades (Total) | 5 |
| Max Open Trades (Per Instrument) | 2 |
| Stop Loss | 1.5× ATR from entry |
| Take Profit 1 | 1:1 RR → close 40% |
| Take Profit 2 | 1:2 RR → close 40% |
| Take Profit 3 | 1:3 RR → trail final 20% |
| Trailing Stop | 0.75× ATR (activates after TP1) |
| Spread Filter | Skip if > 1.5× typical spread |

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
apex_scalper/
│
├── config/
│   ├── settings.py          # ✦ ALL configurable parameters (edit here)
│   └── instruments.py       # Per-asset specs (pip value, sessions, magic numbers)
│
├── src/
│   ├── data/
│   │   ├── oanda_client.py  # Oanda API connection + candle fetching
│   │   └── market_data.py   # Multi-TF data manager + indicator computation
│   │
│   ├── filters/
│   │   ├── regime.py        # Session gate, ATR gate, ADX regime detection
│   │   └── htf_bias.py      # M15 EMA stack, H1 structure, VWAP bias
│   │
│   ├── signals/
│   │   ├── momentum.py      # Module A — EMA cross, RSI, MACD
│   │   ├── mean_reversion.py# Module B — VWAP dev, BB, RSI divergence
│   │   ├── order_flow.py    # Module C — Volume proxy, bar pressure
│   │   ├── smc.py           # Module D — Liquidity sweeps, OB, BOS
│   │   └── scorer.py        # Confluence aggregator (0–10 score)
│   │
│   ├── risk/
│   │   ├── position_sizer.py# ATR-based lot sizing with score tiers
│   │   └── risk_manager.py  # Daily DD, max trades, P&L tracking
│   │
│   ├── execution/           # [Phase 2] MT5 bridge — order routing
│   ├── utils/
│   │   └── logger.py        # Rotating file + console logger
│   │
│   └── main.py              # Backtest entrypoint
│
├── backtests/
│   ├── engine.py            # Bar-by-bar backtest engine (anti-lookahead)
│   ├── report_generator.py  # Investor-grade Excel report generator
│   └── reports/             # Generated Excel reports saved here
│
├── logs/                    # Runtime logs
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

---

## Setup & Installation

### 1. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 2. Configure Credentials

Edit `config/settings.py` and update:

```python
OANDA_ACCOUNT_ID  = "YOUR_ACCOUNT_ID"
OANDA_API_KEY     = "YOUR_API_KEY"
OANDA_ENVIRONMENT = "practice"   # or "live"
```

For MT5 (Phase 2 — live execution):
```python
MT5_LOGIN    = 123456
MT5_PASSWORD = "your_password"
MT5_SERVER   = "BrokerName-Server"
```

### 3. Configure Backtest Parameters

In `config/settings.py`:
```python
BACKTEST_START    = "2024-01-01"
BACKTEST_END      = "2024-12-31"
INITIAL_CAPITAL   = 10_000.0
```

---

## Running the Backtest

```powershell
python -m src.main
```

Output: Excel report saved to `backtests/reports/`

---

## Excel Report Structure

| Sheet | Contents |
|-------|----------|
| Summary | Key metrics, performance ratings, strategy config |
| Per-Instrument | Asset-by-asset breakdown with colour-coded metrics |
| Monthly Returns | Heatmap of P&L by month/year |
| Trade Log | Full trade-by-trade detail |
| Equity Curve | Account growth chart + drawdown data |

---

## Development Phases

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | Backtest engine, signal stack, risk engine, reporting |
| Phase 2 | 🔲 Pending | MT5 execution bridge (order routing, SL/TP management) |
| Phase 3 | 🔲 Pending | Live trading loop (Oanda stream → signal → MT5 execute) |
| Phase 4 | 🔲 Pending | Telegram/Discord trade alerts |
| Phase 5 | 🔲 Pending | Walk-forward optimisation + Monte Carlo simulation |

---

## Indicator Reference

| Indicator | Parameters | Purpose |
|-----------|-----------|---------|
| EMA | 5, 13, 20, 50, 200 | Trend direction, crossovers |
| RSI | 14 | Momentum confirmation, divergence |
| MACD | 12/26/9 | Histogram direction |
| ATR | 14 | Dynamic SL sizing, volatility gate |
| Bollinger Bands | 20, 2σ | Mean reversion extremes |
| ADX | 14 | Regime classification |
| VWAP | Daily anchor | Price fairness reference |

---

*APEX Scalper — Built for precision. Designed for longevity.*
