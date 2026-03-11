# /scripts/02_run_backtest.py
"""
APEX Scalper — Pipeline Step 2: Run Backtest
=============================================
Loads pre-collected Parquet files from data/raw/, runs the bar-by-bar
backtest engine, and saves the full results as a pickle file.

MUST run Step 1 first:
    python -m scripts.01_collect_data

Run from project root:
    python -m scripts.02_run_backtest

Output: data/results/backtest_results.pkl
        (consumed by Steps 3 and 4)
"""

import os
import sys
import pickle
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    INSTRUMENTS, BACKTEST_START, BACKTEST_END,
    INITIAL_CAPITAL, RAW_DATA_DIR, RESULTS_DIR,
)
from config.instruments import get_all_oanda_symbols
from backtests.engine import BacktestEngine
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────
# CONFIGURABLE
# ─────────────────────────────────────────────
TIMEFRAMES       = ["M5", "M15", "H1"]
RESULTS_FILENAME = "backtest_results.pkl"


def load_parquets() -> dict:
    """
    Load all Parquet files from data/raw/ into a nested dict:
        {instrument: {"M5": df, "M15": df, "H1": df}}

    Raises:
        FileNotFoundError if any expected file is missing.
    """
    instruments = get_all_oanda_symbols()
    data = {}

    logger.info("  Loading Parquet files from data/raw/ ...")
    for instrument in instruments:
        data[instrument] = {}
        for tf in TIMEFRAMES:
            path = os.path.join(RAW_DATA_DIR, f"{instrument}_{tf}.parquet")
            if not os.path.exists(path):
                raise FileNotFoundError(
                    f"Missing: {path}\n"
                    f"  → Run Step 1 first:  python -m scripts.01_collect_data"
                )
            df = pd.read_parquet(path)
            data[instrument][tf] = df
            logger.info(f"    {instrument} {tf}: {len(df):,} bars")

    return data


def run_backtest():
    """
    Main entry point. Load parquets → run engine → save results pickle.
    """
    os.makedirs(RESULTS_DIR, exist_ok=True)

    logger.info("=" * 60)
    logger.info("  APEX SCALPER — STEP 2: BACKTEST")
    logger.info("=" * 60)
    logger.info(f"  Period:   {BACKTEST_START} → {BACKTEST_END}")
    logger.info(f"  Capital:  ${INITIAL_CAPITAL:,.2f}")
    logger.info("=" * 60)

    # ── Step A: Load data ─────────────────────────────────────────────────
    try:
        preloaded_data = load_parquets()
    except FileNotFoundError as e:
        logger.error(str(e))
        return

    # ── Step B: Initialise engine ─────────────────────────────────────────
    # BacktestEngine creates its own RiskManager internally — no injection needed.
    engine = BacktestEngine()

    instruments = get_all_oanda_symbols()

    # ── Step C: Run engine with pre-loaded data ───────────────────────────
    # The engine's run() method accepts preloaded_data to skip Oanda fetches.
    # This is the key change vs. running from src/main.py.
    results = engine.run(
        instruments=instruments,
        preloaded_data=preloaded_data,
    )

    # ── Step D: Save results as pickle ────────────────────────────────────
    out_path = os.path.join(RESULTS_DIR, RESULTS_FILENAME)
    with open(out_path, "wb") as f:
        pickle.dump(results, f)

    metrics = results.get("metrics", {})

    logger.info("=" * 60)
    logger.info("  BACKTEST COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Total Trades:   {metrics.get('total_trades', 0):,}")
    logger.info(f"  Win Rate:       {metrics.get('win_rate_pct', 0):.1f}%")
    logger.info(f"  Profit Factor:  {metrics.get('profit_factor', 0):.2f}")
    logger.info(f"  Net P&L:        ${metrics.get('net_pnl', 0):+,.2f}")
    logger.info(f"  Total Return:   {metrics.get('total_return_pct', 0):+.2f}%")
    logger.info(f"  Max Drawdown:   {metrics.get('max_drawdown_pct', 0):.2f}%")
    logger.info(f"  Sharpe Ratio:   {metrics.get('sharpe_ratio', 0):.2f}")
    logger.info(f"  Sortino Ratio:  {metrics.get('sortino_ratio', 0):.2f}")
    logger.info(f"  Calmar Ratio:   {metrics.get('calmar_ratio', 0):.2f}")
    logger.info(f"  Results saved:  {out_path}")
    logger.info("  Next step → python -m scripts.03_plot_results")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_backtest()
