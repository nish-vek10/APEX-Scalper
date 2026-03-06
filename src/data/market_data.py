# /src/data/market_data.py
"""
APEX Scalper — Market Data Manager
=====================================
Manages multi-timeframe OHLCV data for all instruments.
Fetches from Oanda, computes all base indicators, and serves
clean DataFrames to the signal and filter modules.
"""

import pandas as pd
import pandas_ta as ta

from config.settings import (
    TF_ENTRY, TF_BIAS, TF_ANCHOR, LOOKBACK,
    EMA_FAST, EMA_MID, EMA_SLOW, EMA_TREND, EMA_MACRO,
    RSI_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    ATR_PERIOD, BB_PERIOD, BB_STD, ADX_PERIOD,
)
from src.data.oanda_client import OandaClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MarketData:
    """
    Central data hub for APEX Scalper.
    Fetches and caches multi-TF candles per instrument,
    and attaches all required technical indicators to each DataFrame.
    """

    def __init__(self, oanda_client: OandaClient):
        self.client = oanda_client
        # Cache: {instrument: {timeframe: DataFrame}}
        self._cache: dict[str, dict[str, pd.DataFrame]] = {}

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: LOAD & REFRESH DATA
    # ─────────────────────────────────────────────────────────────────────

    def load_instrument(
        self,
        instrument: str,
        from_date: str = None,
        to_date: str = None
    ) -> None:
        """
        Fetch M5, M15, and H1 candles for an instrument,
        compute indicators on each TF, and store in cache.

        Args:
            instrument: Oanda symbol e.g. "XAU_USD"
            from_date:  Start date "YYYY-MM-DD" (backtest mode)
            to_date:    End date "YYYY-MM-DD"   (backtest mode)
                        If both are None, fetches using LOOKBACK count instead.
        """
        logger.info(f"Loading market data for {instrument}...")
        self._cache[instrument] = {}

        for tf in [TF_ENTRY, TF_BIAS, TF_ANCHOR]:
            if from_date and to_date:
                # Backtest mode — fetch full historical range
                df = self.client.get_candles_paginated(
                    instrument=instrument,
                    granularity=tf,
                    from_date=from_date,
                    to_date=to_date
                )
            else:
                # Live mode — fetch recent N candles
                df = self.client.get_candles(
                    instrument=instrument,
                    granularity=tf,
                    count=LOOKBACK[tf]
                )

            if df.empty:
                logger.warning(f"Empty data for {instrument} {tf} — skipping indicators.")
                self._cache[instrument][tf] = df
                continue

            # Attach all technical indicators
            df = self._compute_indicators(df)
            self._cache[instrument][tf] = df
            logger.debug(f"  {tf}: {len(df)} candles with indicators attached.")

        logger.info(f"Market data loaded for {instrument}.")

    def get(self, instrument: str, timeframe: str) -> pd.DataFrame:
        """
        Retrieve the cached indicator-enriched DataFrame for a given instrument + TF.

        Args:
            instrument: Oanda symbol
            timeframe:  "M5" | "M15" | "H1"

        Returns:
            pd.DataFrame with OHLCV + all indicators, or empty DataFrame.
        """
        return self._cache.get(instrument, {}).get(timeframe, pd.DataFrame())

    # ─────────────────────────────────────────────────────────────────────
    # INDICATOR COMPUTATION
    # ─────────────────────────────────────────────────────────────────────

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Attach all required technical indicators to a raw OHLCV DataFrame.
        Uses pandas_ta for clean, vectorised indicator computation.

        Indicators added:
            EMA 5, 13, 20, 50, 200
            RSI(14)
            MACD(12,26,9)
            ATR(14)
            Bollinger Bands(20, 2)
            ADX(14)
            VWAP (anchored daily)
            Volume proxy (bar range)

        Args:
            df: Raw OHLCV DataFrame (index = datetime UTC)

        Returns:
            DataFrame with indicator columns appended.
        """
        df = df.copy()

        # ── EMA Stack ────────────────────────────────────────────────────
        df[f"ema_{EMA_FAST}"]  = ta.ema(df["close"], length=EMA_FAST)
        df[f"ema_{EMA_MID}"]   = ta.ema(df["close"], length=EMA_MID)
        df[f"ema_{EMA_SLOW}"]  = ta.ema(df["close"], length=EMA_SLOW)
        df[f"ema_{EMA_TREND}"] = ta.ema(df["close"], length=EMA_TREND)
        df[f"ema_{EMA_MACRO}"] = ta.ema(df["close"], length=EMA_MACRO)

        # ── RSI ──────────────────────────────────────────────────────────
        df["rsi"] = ta.rsi(df["close"], length=RSI_PERIOD)

        # ── MACD ─────────────────────────────────────────────────────────
        macd_df = ta.macd(
            df["close"],
            fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL
        )
        if macd_df is not None and not macd_df.empty:
            df["macd"]        = macd_df.iloc[:, 0]   # MACD line
            df["macd_signal"] = macd_df.iloc[:, 1]   # Signal line
            df["macd_hist"]   = macd_df.iloc[:, 2]   # Histogram

        # ── ATR ──────────────────────────────────────────────────────────
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=ATR_PERIOD)

        # ── Bollinger Bands ───────────────────────────────────────────────
        bb_df = ta.bbands(df["close"], length=BB_PERIOD, std=BB_STD)
        if bb_df is not None and not bb_df.empty:
            df["bb_lower"] = bb_df.iloc[:, 0]   # Lower band
            df["bb_mid"]   = bb_df.iloc[:, 1]   # Middle band (SMA20)
            df["bb_upper"] = bb_df.iloc[:, 2]   # Upper band

        # ── ADX ──────────────────────────────────────────────────────────
        adx_df = ta.adx(df["high"], df["low"], df["close"], length=ADX_PERIOD)
        if adx_df is not None and not adx_df.empty:
            df["adx"] = adx_df.iloc[:, 0]       # ADX value

        # ── VWAP (Daily Anchor) ───────────────────────────────────────────
        # pandas_ta VWAP requires a 'volume' column; we use tick volume as proxy
        try:
            df["vwap"] = ta.vwap(
                df["high"], df["low"], df["close"], df["volume"],
                anchor="D"    # Reset VWAP anchor daily
            )
        except Exception:
            # Fallback if tick volume is zero (common in CFDs)
            df["vwap"] = df["close"].rolling(20).mean()

        # ── Volume Proxy (Bar Range) ──────────────────────────────────────
        # True volume unreliable on CFDs; use (high-low) / ATR as activity proxy
        df["bar_range"]     = df["high"] - df["low"]
        df["vol_proxy"]     = df["bar_range"]
        df["vol_proxy_avg"] = df["vol_proxy"].rolling(20).mean()
        df["vol_ratio"]     = df["vol_proxy"] / df["vol_proxy_avg"].replace(0, 1)

        # ── VWAP Deviation ─────────────────────────────────────────────────
        # How far price has deviated from VWAP in ATR units
        df["vwap_dev_atr"] = (df["close"] - df["vwap"]) / df["atr"].replace(0, 1)

        # ── EMA Histogram (for crossover detection) ───────────────────────
        df["ema_diff"] = df[f"ema_{EMA_FAST}"] - df[f"ema_{EMA_MID}"]

        # Drop rows with NaN indicators (warmup period)
        df.dropna(subset=["atr", "rsi", f"ema_{EMA_MACRO}"], inplace=True)

        return df