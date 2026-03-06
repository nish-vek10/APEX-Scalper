# /src/filters/htf_bias.py
"""
APEX Scalper — Higher Timeframe Bias Engine
=============================================
Establishes directional bias using M15 and H1 data before M5 entry.
The bias score feeds into the signal scorer as Module E (HTF Alignment Bonus).

Bias sources:
    1. EMA Stack (M15)      — EMA 20/50/200 alignment
    2. Market Structure (H1)— Swing high/low series (HH/HL vs LH/LL)
    3. VWAP Anchor (M5)     — Price vs Daily VWAP
    4. Key Level Proximity  — Distance to prev day high/low, weekly open
"""

import pandas as pd
import numpy as np

from config.settings import EMA_SLOW, EMA_TREND, EMA_MACRO, SWING_LOOKBACK
from src.utils.logger import get_logger

logger = get_logger(__name__)


class HTFBias:
    """
    Computes a directional bias signal from higher timeframe data.
    Returns a bias direction and a confidence score (0–2) for the scorer.
    """

    def evaluate(
        self,
        df_m15: pd.DataFrame,
        df_h1:  pd.DataFrame,
        df_m5:  pd.DataFrame,
    ) -> dict:
        """
        Evaluate HTF bias at the current bar.

        Args:
            df_m15: M15 DataFrame with indicators
            df_h1:  H1 DataFrame with indicators
            df_m5:  M5 DataFrame with indicators (for VWAP check)

        Returns:
            dict with keys:
                bias        (str)   — "long" | "short" | "neutral"
                score       (float) — 0.0–2.0 (used as Module E score)
                ema_bias    (str)   — EMA stack signal
                struct_bias (str)   — Structure signal
                vwap_bias   (str)   — VWAP signal
                detail      (str)   — Human-readable summary
        """
        result = {
            "bias":        "neutral",
            "score":       0.0,
            "ema_bias":    "neutral",
            "struct_bias": "neutral",
            "vwap_bias":   "neutral",
            "detail":      "",
        }

        if df_m15.empty or df_h1.empty or df_m5.empty:
            result["detail"] = "Insufficient HTF data"
            return result

        # ── 1. EMA STACK BIAS (M15) — max 1.0 pt ─────────────────────────
        ema_bias, ema_score = self._ema_stack_bias(df_m15)
        result["ema_bias"] = ema_bias

        # ── 2. MARKET STRUCTURE BIAS (H1) — max 0.5 pt ───────────────────
        struct_bias, struct_score = self._structure_bias(df_h1)
        result["struct_bias"] = struct_bias

        # ── 3. VWAP BIAS (M5) — max 0.5 pt ───────────────────────────────
        vwap_bias, vwap_score = self._vwap_bias(df_m5)
        result["vwap_bias"] = vwap_bias

        # ── AGGREGATE BIAS DIRECTION ──────────────────────────────────────
        long_votes  = sum([1 for b in [ema_bias, struct_bias, vwap_bias] if b == "long"])
        short_votes = sum([1 for b in [ema_bias, struct_bias, vwap_bias] if b == "short"])

        if long_votes >= 2:
            overall_bias = "long"
        elif short_votes >= 2:
            overall_bias = "short"
        else:
            overall_bias = "neutral"

        total_score = ema_score + struct_score + vwap_score  # Max = 2.0

        result["bias"]   = overall_bias
        result["score"]  = round(min(total_score, 2.0), 2)
        result["detail"] = (
            f"HTF Bias: {overall_bias.upper()} | "
            f"EMA: {ema_bias} | Struct: {struct_bias} | VWAP: {vwap_bias} | "
            f"Score: {result['score']}/2.0"
        )
        return result

    # ─────────────────────────────────────────────────────────────────────
    # MODULE 1: EMA STACK (M15)
    # ─────────────────────────────────────────────────────────────────────

    def _ema_stack_bias(self, df_m15: pd.DataFrame) -> tuple[str, float]:
        """
        Determine directional bias from EMA 20/50/200 stack on M15.
        Perfect bull stack: price > EMA20 > EMA50 > EMA200 → long
        Perfect bear stack: price < EMA20 < EMA50 < EMA200 → short

        Returns: (bias: str, score: float) — score up to 1.0
        """
        bar = df_m15.iloc[-1]

        close  = bar.get("close")
        ema20  = bar.get(f"ema_{EMA_SLOW}")
        ema50  = bar.get(f"ema_{EMA_TREND}")
        ema200 = bar.get(f"ema_{EMA_MACRO}")

        if any(pd.isna(v) for v in [close, ema20, ema50, ema200]):
            return "neutral", 0.0

        bull_stack = close > ema20 > ema50 > ema200
        bear_stack = close < ema20 < ema50 < ema200

        # Partial alignment (price above two EMAs)
        bull_partial = close > ema20 and close > ema50
        bear_partial = close < ema20 and close < ema50

        if bull_stack:
            return "long", 1.0
        elif bear_stack:
            return "short", 1.0
        elif bull_partial:
            return "long", 0.5
        elif bear_partial:
            return "short", 0.5
        else:
            return "neutral", 0.0

    # ─────────────────────────────────────────────────────────────────────
    # MODULE 2: MARKET STRUCTURE (H1)
    # ─────────────────────────────────────────────────────────────────────

    def _structure_bias(self, df_h1: pd.DataFrame) -> tuple[str, float]:
        """
        Detect swing high/low structure on H1 to determine trend direction.
        Looks for HH+HL series (bullish) or LH+LL series (bearish).

        Returns: (bias: str, score: float) — score up to 0.5
        """
        if len(df_h1) < SWING_LOOKBACK * 2:
            return "neutral", 0.0

        highs = df_h1["high"].values
        lows  = df_h1["low"].values

        # Find swing highs and lows using simple pivot detection
        swing_highs = self._find_swing_highs(highs, SWING_LOOKBACK)
        swing_lows  = self._find_swing_lows(lows,  SWING_LOOKBACK)

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return "neutral", 0.0

        # Check for Higher Highs + Higher Lows → Bullish structure
        hh = swing_highs[-1] > swing_highs[-2]
        hl = swing_lows[-1]  > swing_lows[-2]

        # Check for Lower Highs + Lower Lows → Bearish structure
        lh = swing_highs[-1] < swing_highs[-2]
        ll = swing_lows[-1]  < swing_lows[-2]

        if hh and hl:
            return "long", 0.5
        elif lh and ll:
            return "short", 0.5
        else:
            return "neutral", 0.0

    def _find_swing_highs(self, highs: np.ndarray, lookback: int) -> list:
        """Return list of swing high values using a simple pivot detection."""
        pivots = []
        for i in range(lookback, len(highs) - lookback):
            if highs[i] == max(highs[i - lookback:i + lookback + 1]):
                pivots.append(highs[i])
        return pivots

    def _find_swing_lows(self, lows: np.ndarray, lookback: int) -> list:
        """Return list of swing low values using a simple pivot detection."""
        pivots = []
        for i in range(lookback, len(lows) - lookback):
            if lows[i] == min(lows[i - lookback:i + lookback + 1]):
                pivots.append(lows[i])
        return pivots

    # ─────────────────────────────────────────────────────────────────────
    # MODULE 3: VWAP BIAS (M5)
    # ─────────────────────────────────────────────────────────────────────

    def _vwap_bias(self, df_m5: pd.DataFrame) -> tuple[str, float]:
        """
        Simple VWAP bias: is price currently above or below daily VWAP?
        Above VWAP → lean long | Below VWAP → lean short.

        Returns: (bias: str, score: float) — score up to 0.5
        """
        bar   = df_m5.iloc[-1]
        close = bar.get("close")
        vwap  = bar.get("vwap")

        if pd.isna(close) or pd.isna(vwap):
            return "neutral", 0.0

        if close > vwap:
            return "long", 0.5
        elif close < vwap:
            return "short", 0.5
        else:
            return "neutral", 0.0