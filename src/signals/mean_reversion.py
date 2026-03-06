# /src/signals/mean_reversion.py
"""
APEX Scalper — Signal Module B: Mean Reversion
================================================
Identifies stretched price conditions that are likely to snap back.
Trades are triggered when price is overextended from VWAP + Bollinger Band
edges, with RSI divergence as an optional confirmer.
Maximum score: 2.0 points.

Scoring breakdown:
    VWAP deviation > 1.5x ATR   → 1.0 pt
    BB outer band touch/breach   → 0.5 pt
    RSI divergence detected      → 0.5 pt
"""

import pandas as pd
import numpy as np

from config.settings import VWAP_DEVIATION_ATR_MULTIPLIER
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MeanReversionSignal:
    """
    Module B — Mean reversion signal evaluator.
    Operates on the M5 entry timeframe.
    Note: Mean reversion signals are COUNTER-TREND relative to recent move.
    Direction is opposite to the stretch direction.
    """

    def evaluate(self, df_m5: pd.DataFrame) -> dict:
        """
        Evaluate mean reversion conditions on the current M5 bar.

        Args:
            df_m5: M5 DataFrame with indicators, up to and including current bar.

        Returns:
            dict with keys:
                direction     (str)   — "long" | "short" | "neutral"
                score         (float) — 0.0–2.0
                vwap_stretched(bool)  — price is stretched from VWAP
                bb_extreme    (bool)  — price is at BB outer band
                rsi_divergence(bool)  — RSI divergence detected
                detail        (str)   — Human-readable breakdown
        """
        result = {
            "direction":      "neutral",
            "score":          0.0,
            "vwap_stretched": False,
            "bb_extreme":     False,
            "rsi_divergence": False,
            "detail":         "",
        }

        if len(df_m5) < 5:
            result["detail"] = "Insufficient bars for mean reversion check"
            return result

        curr = df_m5.iloc[-1]

        close        = curr.get("close")
        vwap         = curr.get("vwap")
        atr          = curr.get("atr")
        bb_upper     = curr.get("bb_upper")
        bb_lower     = curr.get("bb_lower")
        rsi          = curr.get("rsi")
        vwap_dev_atr = curr.get("vwap_dev_atr")

        if any(pd.isna(v) for v in [close, vwap, atr, bb_upper, bb_lower]):
            result["detail"] = "Required indicator values unavailable"
            return result

        direction  = "neutral"
        vwap_score = 0.0
        bb_score   = 0.0
        div_score  = 0.0

        # ── 1. VWAP DEVIATION (1.0 pt) ────────────────────────────────────
        # Price stretched far above VWAP → fade long, expect reversion down
        # Price stretched far below VWAP → fade short, expect reversion up
        if not pd.isna(vwap_dev_atr):
            if vwap_dev_atr > VWAP_DEVIATION_ATR_MULTIPLIER:
                # Price overextended above VWAP → short reversion trade
                direction  = "short"
                vwap_score = 1.0
                result["vwap_stretched"] = True
            elif vwap_dev_atr < -VWAP_DEVIATION_ATR_MULTIPLIER:
                # Price overextended below VWAP → long reversion trade
                direction  = "long"
                vwap_score = 1.0
                result["vwap_stretched"] = True

        if direction == "neutral":
            result["detail"] = "Price not stretched enough from VWAP for mean reversion"
            return result

        # ── 2. BOLLINGER BAND EXTREME (0.5 pt) ───────────────────────────
        # Additional confirmation that price is at statistical extreme
        if direction == "short" and close >= bb_upper:
            bb_score = 0.5
            result["bb_extreme"] = True
        elif direction == "long" and close <= bb_lower:
            bb_score = 0.5
            result["bb_extreme"] = True

        # ── 3. RSI DIVERGENCE (0.5 pt) ────────────────────────────────────
        # Bearish divergence: price making higher high but RSI making lower high
        # Bullish divergence: price making lower low but RSI making higher low
        rsi_div_detected = self._detect_rsi_divergence(df_m5, direction)
        if rsi_div_detected:
            div_score = 0.5
            result["rsi_divergence"] = True

        total_score = vwap_score + bb_score + div_score

        result["direction"] = direction
        result["score"]     = round(min(total_score, 2.0), 2)
        result["detail"]    = (
            f"MeanRev [{direction.upper()}] | "
            f"VWAP dev: {vwap_dev_atr:.2f}x ATR ({vwap_score:.1f}pt) | "
            f"BB extreme: {result['bb_extreme']} ({bb_score:.1f}pt) | "
            f"RSI div: {result['rsi_divergence']} ({div_score:.1f}pt) | "
            f"Total: {result['score']}/2.0"
        )
        return result

    # ─────────────────────────────────────────────────────────────────────
    # HELPER: RSI DIVERGENCE DETECTION
    # ─────────────────────────────────────────────────────────────────────

    def _detect_rsi_divergence(self, df: pd.DataFrame, direction: str, lookback: int = 10) -> bool:
        """
        Detect simple RSI divergence over the last `lookback` bars.

        Bearish divergence: price HH but RSI LH over recent bars.
        Bullish divergence: price LL but RSI HL over recent bars.

        Args:
            df:        M5 DataFrame
            direction: Expected reversion direction ("long" = bullish div, "short" = bearish div)
            lookback:  Bars to look back for divergence check

        Returns:
            True if divergence detected.
        """
        if len(df) < lookback + 1:
            return False

        recent = df.tail(lookback)

        price_now = recent["close"].iloc[-1]
        price_ago = recent["close"].iloc[0]
        rsi_now   = recent["rsi"].iloc[-1]
        rsi_ago   = recent["rsi"].iloc[0]

        if pd.isna(rsi_now) or pd.isna(rsi_ago):
            return False

        if direction == "short":
            # Bearish divergence: price going up but RSI going down
            return (price_now > price_ago) and (rsi_now < rsi_ago)
        elif direction == "long":
            # Bullish divergence: price going down but RSI going up
            return (price_now < price_ago) and (rsi_now > rsi_ago)

        return False