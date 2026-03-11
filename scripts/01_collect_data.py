# /scripts/01_collect_data.py
"""
APEX Scalper — Pipeline Step 1: Data Collection
=================================================
Fetches M5, M15, H1 OHLCV candles from Oanda for every configured
instrument, computes all technical indicators, and saves each
timeframe as a Parquet file.

Parquet format gives fast columnar reads — loading a 150k-bar file
takes ~50ms vs. several seconds for CSV.

Output: data/raw/{INSTRUMENT}_{TIMEFRAME}.parquet

Run from project root:
    python -m scripts.01_collect_data

Re-running will overwrite existing files with fresh data.
"""

import os
import sys
import pandas as pd
import pandas_ta as ta

# Allow imports from project root when running as a module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    INSTRUMENTS, BACKTEST_START, BACKTEST_END,
    RAW_DATA_DIR,
    EMA_FAST, EMA_MID, EMA_SLOW, EMA_TREND, EMA_MACRO,
    RSI_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    ATR_PERIOD, BB_PERIOD, BB_STD, ADX_PERIOD,
)
from src.data.oanda_client import OandaClient
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────
# CONFIGURABLE — edit here if needed
# ─────────────────────────────────────────────
TIMEFRAMES = ["M5", "M15", "H1"]
FROM_DATE  = BACKTEST_START
TO_DATE    = BACKTEST_END
OUTPUT_DIR = RAW_DATA_DIR


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Attach all technical indicators to a raw OHLCV DataFrame.
    Indicators are computed once here so the backtest engine reads
    them directly without recomputing each bar.

    Args:
        df: Raw OHLCV DataFrame with columns [open, high, low, close, volume]

    Returns:
        DataFrame with all indicator columns appended, warmup rows dropped.
    """
    df = df.copy()

    # ── EMA stack (5 / 13 / 20 / 50 / 200) ─────────────────────────────
    df[f"ema_{EMA_FAST}"]  = ta.ema(df["close"], length=EMA_FAST)
    df[f"ema_{EMA_MID}"]   = ta.ema(df["close"], length=EMA_MID)
    df[f"ema_{EMA_SLOW}"]  = ta.ema(df["close"], length=EMA_SLOW)
    df[f"ema_{EMA_TREND}"] = ta.ema(df["close"], length=EMA_TREND)
    df[f"ema_{EMA_MACRO}"] = ta.ema(df["close"], length=EMA_MACRO)

    # ── RSI ──────────────────────────────────────────────────────────────
    df["rsi"] = ta.rsi(df["close"], length=RSI_PERIOD)

    # ── MACD ─────────────────────────────────────────────────────────────
    macd = ta.macd(df["close"], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
    if macd is not None and not macd.empty:
        df["macd"]        = macd.iloc[:, 0]   # MACD line
        df["macd_signal"] = macd.iloc[:, 1]   # Signal line
        df["macd_hist"]   = macd.iloc[:, 2]   # Histogram

    # ── ATR ──────────────────────────────────────────────────────────────
    df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=ATR_PERIOD)

    # ── Bollinger Bands ──────────────────────────────────────────────────
    bb = ta.bbands(df["close"], length=BB_PERIOD, std=BB_STD)
    if bb is not None and not bb.empty:
        df["bb_lower"] = bb.iloc[:, 0]
        df["bb_mid"]   = bb.iloc[:, 1]
        df["bb_upper"] = bb.iloc[:, 2]

    # ── ADX ──────────────────────────────────────────────────────────────
    adx = ta.adx(df["high"], df["low"], df["close"], length=ADX_PERIOD)
    if adx is not None and not adx.empty:
        df["adx"] = adx.iloc[:, 0]

    # ── VWAP (daily anchor, fallback to SMA20 if tick volume is zero) ────
    try:
        vwap = ta.vwap(df["high"], df["low"], df["close"], df["volume"], anchor="D")
        df["vwap"] = vwap if vwap is not None else df["close"].rolling(20).mean()
    except Exception:
        df["vwap"] = df["close"].rolling(20).mean()

    # ── Volume proxy (bar range / ATR) — CFDs lack true tick volume ──────
    df["bar_range"]     = df["high"] - df["low"]
    df["vol_proxy"]     = df["bar_range"]
    df["vol_proxy_avg"] = df["vol_proxy"].rolling(20).mean()
    df["vol_ratio"]     = df["vol_proxy"] / df["vol_proxy_avg"].replace(0, 1)

    # ── VWAP deviation in ATR units ──────────────────────────────────────
    df["vwap_dev_atr"] = (df["close"] - df["vwap"]) / df["atr"].replace(0, 1)

    # ── EMA diff (used for crossover detection in momentum module) ───────
    df["ema_diff"] = df[f"ema_{EMA_FAST}"] - df[f"ema_{EMA_MID}"]

    # Drop bars where key indicators haven't stabilised (EMA200 warmup = 200 bars)
    df.dropna(subset=["atr", "rsi", f"ema_{EMA_MACRO}"], inplace=True)

    return df


def collect_all():
    """
    Main entry point. Fetch all instruments × timeframes, compute
    indicators, save each as a Parquet file.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    client   = OandaClient()
    total    = len(INSTRUMENTS) * len(TIMEFRAMES)
    done     = 0
    failures = []

    logger.info("=" * 60)
    logger.info("  APEX SCALPER — STEP 1: DATA COLLECTION")
    logger.info("=" * 60)
    logger.info(f"  Period:      {FROM_DATE} → {TO_DATE}")
    logger.info(f"  Instruments: {list(INSTRUMENTS.keys())}")
    logger.info(f"  Timeframes:  {TIMEFRAMES}")
    logger.info(f"  Output:      {OUTPUT_DIR}/")
    logger.info("=" * 60)

    for instrument in INSTRUMENTS.keys():
        for tf in TIMEFRAMES:
            done += 1
            logger.info(f"  [{done}/{total}] Fetching {instrument} {tf} ...")

            try:
                # Paginated fetch — handles Oanda's 5000-candle-per-request limit
                df = client.get_candles_paginated(
                    instrument=instrument,
                    granularity=tf,
                    from_date=FROM_DATE,
                    to_date=TO_DATE,
                )

                if df.empty:
                    logger.warning(f"    No data returned — skipping.")
                    failures.append(f"{instrument}_{tf}")
                    continue

                raw_bars = len(df)
                df = compute_indicators(df)

                filepath = os.path.join(OUTPUT_DIR, f"{instrument}_{tf}.parquet")
                df.to_parquet(filepath)

                logger.info(
                    f"    Saved: {len(df):,} bars (raw: {raw_bars:,}, "
                    f"warmup dropped: {raw_bars - len(df)}) → {filepath}"
                )

            except Exception as e:
                logger.error(f"    FAILED: {instrument} {tf} | {e}")
                failures.append(f"{instrument}_{tf}")

    # ── Final summary ─────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info(f"  Done. Success: {total - len(failures)}/{total}")
    if failures:
        logger.warning(f"  Failed:  {failures}")
    logger.info(f"  Parquets saved to: {OUTPUT_DIR}/")
    logger.info("  Next step → python -m scripts.02_run_backtest")
    logger.info("=" * 60)


if __name__ == "__main__":
    collect_all()
