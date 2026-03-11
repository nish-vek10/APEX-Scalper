# /config/settings.py
"""
APEX Scalper — Global Configuration
====================================
All configurable parameters are defined here.
Modify this file to tune strategy behaviour without touching core logic.
"""

# ─────────────────────────────────────────────
# OANDA API CREDENTIALS
# ─────────────────────────────────────────────
OANDA_ACCOUNT_ID    = "001-004-17523704-003"          # Oanda account ID
OANDA_API_KEY       = "37ee33b35f88e073a08d533849f7a24b-524c89ef15f36cfe532f0918a6aee4c2"             # Oanda API token
OANDA_ENVIRONMENT   = "practice"                 # "practice" | "live"

# ─────────────────────────────────────────────
# BACKTESTING
# ─────────────────────────────────────────────
BACKTEST_START      = "2024-01-01"      # Backtest start date (YYYY-MM-DD)
BACKTEST_END        = "2026-03-05"      # Backtest end date (YYYY-MM-DD)
INITIAL_CAPITAL     = 10_000.0          # Starting account balance (USD)
COMMISSION_PER_LOT  = 3.50              # Round-trip commission per lot (USD)
SLIPPAGE_PIPS       = 0.5               # Assumed slippage in pips per fill

# ─────────────────────────────────────────────
# MT5 CONNECTION
# ─────────────────────────────────────────────
MT5_LOGIN           = 0                          # MT5 account number
MT5_PASSWORD        = "YOUR_MT5_PASSWORD"        # MT5 account password
MT5_SERVER          = "YOUR_BROKER_SERVER"       # MT5 broker server name

# ─────────────────────────────────────────────
# INSTRUMENTS IN SCOPE
# ─────────────────────────────────────────────
# Oanda instrument names → MT5 symbol names
INSTRUMENTS = {
    "XAU_USD":    "XAUUSD",     # Gold
    "SPX500_USD": "SP500",      # S&P 500
    "DE30_EUR":   "GER30",      # DAX
    "US30_USD":   "US30",       # Dow Jones
    "NAS100_USD": "NAS100",     # Nasdaq 100
}

# ─────────────────────────────────────────────
# TIMEFRAMES
# ─────────────────────────────────────────────
TF_ENTRY    = "M5"    # Primary entry timeframe
TF_BIAS     = "M15"   # Mid-level bias timeframe
TF_ANCHOR   = "H1"    # Macro bias / structure timeframe

# Candle lookback per timeframe (how many candles to fetch)
LOOKBACK = {
    "M5":  500,    # ~41 hours of M5 data
    "M15": 300,    # ~75 hours of M15 data
    "H1":  200,    # ~200 hours of H1 data
}

# ─────────────────────────────────────────────
# RISK MANAGEMENT
# ─────────────────────────────────────────────
BASE_RISK_PCT       = 0.005    # 0.5% account risk per trade (base)

# Score-tiered position sizing multipliers
SCORE_SIZE_TIERS = {
    (5, 6):  0.50,    # Minimum confluence  → 50% of base risk
    (7, 8):  0.75,   # Good confluence     → 75% of base risk
    (9, 10): 1.00,    # Maximum confluence  → 100% of base risk
}

MAX_RISK_PCT        = 0.01     # Hard cap — never risk more than 1% per trade
DAILY_DRAWDOWN_LIMIT= 0.05     # -5% daily drawdown → algo shuts down for the day
MAX_OPEN_TRADES_TOTAL = 12      # Maximum concurrent open trades across all instruments
MAX_OPEN_TRADES_PER_INSTRUMENT = 3  # Max concurrent trades per single instrument

# ─────────────────────────────────────────────
# STOP LOSS & TAKE PROFIT
# ─────────────────────────────────────────────
SL_ATR_MULTIPLIER   = 1.5     # Stop loss = entry ± (ATR * this value)

# Tiered take profit RR ratios and position close fractions
TP_TIERS = [
    {"rr": 1.0, "close_pct": 0.40},   # TP1: 1:1 RR → close 40%
    {"rr": 2.0, "close_pct": 0.40},   # TP2: 1:2 RR → close 40%
    {"rr": 3.0, "close_pct": 0.20},   # TP3: 1:3 RR → trail final 20%
]

TRAILING_STOP_ATR_MULTIPLIER = 0.75   # Trailing stop = 0.75x ATR after TP1 hit

# ─────────────────────────────────────────────
# REGIME FILTER THRESHOLDS
# ─────────────────────────────────────────────
ADX_TREND_THRESHOLD     = 20     # ADX > 20 → trending regime
ATR_FLOOR_MULTIPLIER    = 0.5    # ATR must be > 50% of its 20-bar average
ATR_CEILING_MULTIPLIER  = 3.0    # ATR must be < 3x its 20-bar average (news spike filter)
MAX_SPREAD_MULTIPLIER   = 1.5    # Skip trade if spread > 1.5x normal average spread

# ─────────────────────────────────────────────
# INDICATOR PARAMETERS
# ─────────────────────────────────────────────
# EMA periods
EMA_FAST        = 5
EMA_MID         = 13
EMA_SLOW        = 20
EMA_TREND       = 50
EMA_MACRO       = 200

# RSI
RSI_PERIOD      = 14
RSI_LONG_THRESHOLD  = 55   # RSI must be above this for long signals
RSI_SHORT_THRESHOLD = 45   # RSI must be below this for short signals

# MACD
MACD_FAST       = 12
MACD_SLOW       = 26
MACD_SIGNAL     = 9

# ATR
ATR_PERIOD      = 14

# Bollinger Bands
BB_PERIOD       = 20
BB_STD          = 2.0

# ADX
ADX_PERIOD      = 14

# Volume (proxy via bar range since Oanda CFDs lack true volume)
VOLUME_LOOKBACK = 20       # Bars to average for volume proxy baseline

# VWAP deviation threshold for mean reversion
VWAP_DEVIATION_ATR_MULTIPLIER = 1.5   # Price > 1.5x ATR from VWAP = stretched

# SMC — swing detection lookback
SWING_LOOKBACK  = 10       # Bars to look back for swing high/low detection

# ─────────────────────────────────────────────
# SIGNAL SCORING
# ─────────────────────────────────────────────
MIN_SCORE_TO_TRADE  = 5    # Minimum confluence score required to fire a trade
MAX_SCORE           = 10   # Maximum possible score

# ─────────────────────────────────────────────
# NEWS BLACKOUT
# ─────────────────────────────────────────────
NEWS_BLACKOUT_MINUTES = 15   # Pause trading ±15 min around high-impact events

# ─────────────────────────────────────────────
# DATA PIPELINE PATHS
# ─────────────────────────────────────────────
RAW_DATA_DIR    = "data/raw"         # Parquet files saved by 01_collect_data
RESULTS_DIR     = "data/results"     # Backtest pickle saved by 02_run_backtest
PLOTS_DIR       = "data/plots"       # PNG charts saved by 03_plot_results
REPORTS_DIR     = "backtests/reports"  # Excel reports saved by 04_generate_report

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
LOG_LEVEL           = "INFO"                        # DEBUG | INFO | WARNING | ERROR
LOG_FILE            = "logs/apex_scalper.log"       # Log file path
TRADE_LOG_FILE      = "logs/trade_log.csv"          # Individual trade log (CSV)
