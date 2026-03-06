# /src/main.py
"""
APEX Scalper — Main Entry Point
==================================
Runs the APEX Scalper backtest engine across all configured instruments
and generates a full investor-grade Excel performance report.

Run from project root (PowerShell):
    python -m src.main

All configurable parameters (dates, capital, risk) are in config/settings.py
"""

import os
import sys

# Ensure project root is on the path for clean imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    BACKTEST_START,
    BACKTEST_END,
    INITIAL_CAPITAL,
    INSTRUMENTS,
)
from backtests.engine import BacktestEngine
from backtests.report_generator import ReportGenerator
from src.utils.logger import get_logger

logger = get_logger(__name__)


def run_backtest():
    """
    Orchestrates the full backtest workflow:
        1. Instantiate and run the BacktestEngine
        2. Pass results to the ReportGenerator
        3. Save Excel report to backtests/reports/
    """
    logger.info("=" * 60)
    logger.info("  APEX SCALPER — BACKTEST MODE")
    logger.info("=" * 60)
    logger.info(f"  Period:     {BACKTEST_START} → {BACKTEST_END}")
    logger.info(f"  Capital:    ${INITIAL_CAPITAL:,.2f}")
    logger.info(f"  Instruments: {list(INSTRUMENTS.keys())}")
    logger.info("=" * 60)

    # ── Step 1: Run Backtest ──────────────────────────────────────────────
    engine = BacktestEngine()

    results = engine.run(
        instruments=list(INSTRUMENTS.keys()),
        from_date=BACKTEST_START,
        to_date=BACKTEST_END,
    )

    trades       = results["trades"]
    equity_curve = results["equity_curve"]
    metrics      = results["metrics"]

    if not trades:
        logger.warning("No trades were executed during the backtest period.")
        logger.warning("Check your date range, instrument config, and Oanda credentials.")
        return

    # ── Step 2: Generate Report ───────────────────────────────────────────
    reporter     = ReportGenerator()
    report_path  = reporter.generate(
        metrics=metrics,
        trades=trades,
        equity_curve=equity_curve,
    )

    # ── Step 3: Print Summary ─────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("  BACKTEST COMPLETE — SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Total Trades:   {metrics.get('total_trades', 0)}")
    logger.info(f"  Win Rate:       {metrics.get('win_rate_pct', 0):.1f}%")
    logger.info(f"  Profit Factor:  {metrics.get('profit_factor', 0):.2f}")
    logger.info(f"  Net P&L:        ${metrics.get('net_pnl', 0):+,.2f}")
    logger.info(f"  Total Return:   {metrics.get('total_return_pct', 0):+.2f}%")
    logger.info(f"  Max Drawdown:   {metrics.get('max_drawdown_pct', 0):.2f}%")
    logger.info(f"  Sharpe Ratio:   {metrics.get('sharpe_ratio', 0):.2f}")
    logger.info(f"  Sortino Ratio:  {metrics.get('sortino_ratio', 0):.2f}")
    logger.info(f"  Calmar Ratio:   {metrics.get('calmar_ratio', 0):.2f}")
    logger.info("=" * 60)
    logger.info(f"  Report saved:   {report_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_backtest()
