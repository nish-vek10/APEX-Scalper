# /src/signals/momentum.py
"""
APEX Scalper — Signal Module A: Momentum
==========================================
Detects directional momentum via EMA crossover, RSI level, and MACD histogram.
Maximum score: 2.0 points.

Scoring breakdown:
    EMA 5 × EMA 13 crossover   → 1.0 pt
    RSI threshold breach        → 0.5 pt
    MACD histogram direction    → 0.5 pt
"""

import pandas as pd

from config.settings import (
    EMA_FAST, EMA_MID,
    RSI_LONG_THRESHOLD, RSI_SHORT_THRESHOLD,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MomentumSignal:
    """
    Module A — Momentum signal evaluator.
    Operates on the M5 entry timeframe.
    """

    def evaluate(self, df_m5: pd.DataFrame) -> dict:
        """
        Evaluate momentum signals on the current M5 bar.

        Args:
            df_m5: M5 DataFrame with indicators, up to and including current bar.

        Returns:
            dict with keys:
                direction  (str)   — "long" | "short" | "neutral"
                score      (float) — 0.0–2.0
                ema_cross  (bool)  — True if crossover detected this bar
                rsi_ok     (bool)  — True if RSI confirms direction
                macd_ok    (bool)  — True if MACD histogram confirms direction
                detail     (str)   — Human-readable breakdown
        """
        result = {
            "direction": "neutral",
            "score":     0.0,
            "ema_cross": False,
            "rsi_ok":    False,
            "macd_ok":   False,
            "detail":    "",
        }

        # Need at least 2 bars to detect a crossover (current + previous)
        if len(df_m5) < 2:
            result["detail"] = "Insufficient bars for momentum check"
            return result

        curr = df_m5.iloc[-1]
        prev = df_m5.iloc[-2]

        ema_fast_curr = curr.get(f"ema_{EMA_FAST}")
        ema_mid_curr  = curr.get(f"ema_{EMA_MID}")
        ema_fast_prev = prev.get(f"ema_{EMA_FAST}")
        ema_mid_prev  = prev.get(f"ema_{EMA_MID}")
        rsi           = curr.get("rsi")
        macd_hist     = curr.get("macd_hist")

        if any(pd.isna(v) for v in [ema_fast_curr, ema_mid_curr, ema_fast_prev, ema_mid_prev]):
            result["detail"] = "EMA values unavailable"
            return result

        # ── DETERMINE EMA CROSS DIRECTION ────────────────────────────────
        # A crossover happens when the relationship between fast/mid flips bar-to-bar
        bullish_cross = (ema_fast_prev <= ema_mid_prev) and (ema_fast_curr > ema_mid_curr)
        bearish_cross = (ema_fast_prev >= ema_mid_prev) and (ema_fast_curr < ema_mid_curr)

        # If no fresh crossover, check if EMAs are still aligned (continuation)
        bull_aligned = ema_fast_curr > ema_mid_curr
        bear_aligned = ema_fast_curr < ema_mid_curr

        # Assign direction — crossovers score more than plain alignment
        if bullish_cross or bull_aligned:
            direction = "long"
            ema_score = 1.0 if bullish_cross else 0.5   # Fresh cross scores higher
            result["ema_cross"] = bullish_cross
        elif bearish_cross or bear_aligned:
            direction = "short"
            ema_score = 1.0 if bearish_cross else 0.5
            result["ema_cross"] = bearish_cross
        else:
            direction = "neutral"
            ema_score = 0.0

        if direction == "neutral":
            result["detail"] = "No EMA momentum signal"
            return result

        # ── RSI CONFIRMATION ──────────────────────────────────────────────
        rsi_score = 0.0
        if not pd.isna(rsi):
            if direction == "long"  and rsi > RSI_LONG_THRESHOLD:
                rsi_score = 0.5
                result["rsi_ok"] = True
            elif direction == "short" and rsi < RSI_SHORT_THRESHOLD:
                rsi_score = 0.5
                result["rsi_ok"] = True

        # ── MACD HISTOGRAM CONFIRMATION ───────────────────────────────────
        macd_score = 0.0
        if not pd.isna(macd_hist):
            if direction == "long"  and macd_hist > 0:
                macd_score = 0.5
                result["macd_ok"] = True
            elif direction == "short" and macd_hist < 0:
                macd_score = 0.5
                result["macd_ok"] = True

        total_score = ema_score + rsi_score + macd_score

        result["direction"] = direction
        result["score"]     = round(min(total_score, 2.0), 2)
        result["detail"]    = (
            f"Momentum [{direction.upper()}] | "
            f"EMA: {ema_score:.1f} | RSI({rsi:.1f}): {rsi_score:.1f} | "
            f"MACD hist: {macd_score:.1f} | Total: {result['score']}/2.0"
        )
        return result