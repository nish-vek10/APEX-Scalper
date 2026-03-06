# /src/signals/smc.py
"""
APEX Scalper — Signal Module D: SMC / Liquidity
=================================================
Smart Money Concepts (SMC) based signals:
    - Liquidity sweeps of prior swing highs/lows
    - Order block identification and rejection
    - Break of Structure (BOS) confirmation

Maximum score: 2.0 points.

Scoring breakdown:
    Liquidity sweep (sweep + rejection) → 1.0 pt
    Order block rejection               → 0.5 pt
    Break of Structure (BOS)            → 0.5 pt
"""

import pandas as pd
import numpy as np

from config.settings import SWING_LOOKBACK
from src.utils.logger import get_logger

logger = get_logger(__name__)

# How many bars after a swing to look for the sweep
SWEEP_LOOKBACK = 20

# Order block lookback — how many bars back to identify OBs
OB_LOOKBACK = 15


class SMCSignal:
    """
    Module D — Smart Money Concepts signal evaluator.
    Operates primarily on M5, with structure awareness from M15.
    """

    def evaluate(self, df_m5: pd.DataFrame, df_m15: pd.DataFrame = None) -> dict:
        """
        Evaluate SMC/liquidity signals on the current bar.

        Args:
            df_m5:  M5 DataFrame with indicators
            df_m15: M15 DataFrame (optional, for structure context)

        Returns:
            dict with keys:
                direction    (str)   — "long" | "short" | "neutral"
                score        (float) — 0.0–2.0
                swept        (bool)  — liquidity sweep detected
                ob_rejection (bool)  — order block rejection detected
                bos          (bool)  — break of structure confirmed
                detail       (str)   — Human-readable breakdown
        """
        result = {
            "direction":    "neutral",
            "score":        0.0,
            "swept":        False,
            "ob_rejection": False,
            "bos":          False,
            "detail":       "",
        }

        min_bars = max(SWING_LOOKBACK * 2, OB_LOOKBACK + 5)
        if len(df_m5) < min_bars:
            result["detail"] = "Insufficient bars for SMC analysis"
            return result

        curr = df_m5.iloc[-1]
        sweep_score = 0.0
        ob_score    = 0.0
        bos_score   = 0.0
        direction   = "neutral"

        # ── 1. LIQUIDITY SWEEP DETECTION (1.0 pt) ─────────────────────────
        sweep_result = self._detect_liquidity_sweep(df_m5)
        if sweep_result["detected"]:
            sweep_score = 1.0
            direction   = sweep_result["direction"]
            result["swept"] = True

        # ── 2. ORDER BLOCK REJECTION (0.5 pt) ─────────────────────────────
        ob_result = self._detect_order_block_rejection(df_m5, direction)
        if ob_result["detected"]:
            ob_score = 0.5
            result["ob_rejection"] = True
            # OB can also provide direction if sweep didn't
            if direction == "neutral":
                direction = ob_result["direction"]

        # ── 3. BREAK OF STRUCTURE (0.5 pt) ────────────────────────────────
        bos_result = self._detect_break_of_structure(df_m5, direction)
        if bos_result["detected"]:
            bos_score = 0.5
            result["bos"] = True

        total_score = sweep_score + ob_score + bos_score

        # Only emit signal if sweep OR (OB + BOS) detected
        if not result["swept"] and not (result["ob_rejection"] and result["bos"]):
            direction   = "neutral"
            total_score = 0.0

        result["direction"] = direction
        result["score"]     = round(min(total_score, 2.0), 2)
        result["detail"]    = (
            f"SMC [{direction.upper()}] | "
            f"Sweep: {result['swept']} ({sweep_score:.1f}pt) | "
            f"OB reject: {result['ob_rejection']} ({ob_score:.1f}pt) | "
            f"BOS: {result['bos']} ({bos_score:.1f}pt) | "
            f"Total: {result['score']}/2.0"
        )
        return result

    # ─────────────────────────────────────────────────────────────────────
    # LIQUIDITY SWEEP DETECTION
    # ─────────────────────────────────────────────────────────────────────

    def _detect_liquidity_sweep(self, df: pd.DataFrame) -> dict:
        """
        Detect a liquidity sweep: price temporarily breaks a prior swing
        high/low (grabbing stop-loss orders), then rejects sharply.

        A sweep is confirmed when:
        - The current bar's wick extended beyond the swing high/low
        - But the bar CLOSED back inside the range (rejection candle)

        Returns: dict {detected: bool, direction: str}
        """
        result = {"detected": False, "direction": "neutral"}

        recent = df.tail(SWEEP_LOOKBACK + 5)
        if len(recent) < 10:
            return result

        # Define prior swing high/low from the lookback window (excluding last 3 bars)
        prior = recent.iloc[:-3]
        if prior.empty:
            return result

        prior_swing_high = prior["high"].max()
        prior_swing_low  = prior["low"].min()

        curr = df.iloc[-1]
        curr_high  = curr["high"]
        curr_low   = curr["low"]
        curr_close = curr["close"]
        curr_open  = curr["open"]

        # ── BEARISH SWEEP: wick above prior high, close back below ────────
        # Price grabbed liquidity above the swing high then rejected
        if curr_high > prior_swing_high and curr_close < prior_swing_high:
            result["detected"]  = True
            result["direction"] = "short"   # Sweep high → expect move down
            return result

        # ── BULLISH SWEEP: wick below prior low, close back above ─────────
        # Price grabbed liquidity below the swing low then rejected
        if curr_low < prior_swing_low and curr_close > prior_swing_low:
            result["detected"]  = True
            result["direction"] = "long"    # Sweep low → expect move up
            return result

        return result

    # ─────────────────────────────────────────────────────────────────────
    # ORDER BLOCK DETECTION
    # ─────────────────────────────────────────────────────────────────────

    def _detect_order_block_rejection(self, df: pd.DataFrame, bias: str) -> dict:
        """
        Identify the most recent order block (last strong directional candle
        before a significant move) and check if current price is rejecting from it.

        A bullish OB = last bearish candle before a strong bullish impulse.
        A bearish OB = last bullish candle before a strong bearish impulse.

        Returns: dict {detected: bool, direction: str, ob_level: float}
        """
        result = {"detected": False, "direction": "neutral", "ob_level": None}

        if len(df) < OB_LOOKBACK + 5:
            return result

        recent = df.tail(OB_LOOKBACK + 5)
        curr   = df.iloc[-1]
        curr_close = curr["close"]
        curr_atr   = curr.get("atr", None)

        if pd.isna(curr_atr) or curr_atr == 0:
            return result

        # Find the order block level: look for the last opposing candle
        # before a strong impulse in the direction of our bias
        for i in range(len(recent) - 4, 1, -1):
            bar     = recent.iloc[i]
            bar_body = abs(bar["close"] - bar["open"])

            if bias == "long":
                # Bullish OB: last bearish candle (red) before a bullish push
                is_bearish_ob = bar["close"] < bar["open"]
                if is_bearish_ob and bar_body > 0:
                    ob_level = bar["high"]    # Top of the bearish OB candle
                    # Is current price reacting to this level (within 1x ATR)?
                    if abs(curr_close - ob_level) <= curr_atr:
                        result["detected"]  = True
                        result["direction"] = "long"
                        result["ob_level"]  = ob_level
                        return result

            elif bias == "short":
                # Bearish OB: last bullish candle (green) before a bearish push
                is_bullish_ob = bar["close"] > bar["open"]
                if is_bullish_ob and bar_body > 0:
                    ob_level = bar["low"]     # Bottom of the bullish OB candle
                    if abs(curr_close - ob_level) <= curr_atr:
                        result["detected"]  = True
                        result["direction"] = "short"
                        result["ob_level"]  = ob_level
                        return result

        return result

    # ─────────────────────────────────────────────────────────────────────
    # BREAK OF STRUCTURE DETECTION
    # ─────────────────────────────────────────────────────────────────────

    def _detect_break_of_structure(self, df: pd.DataFrame, direction: str) -> dict:
        """
        Confirm a break of structure (BOS) — when price closes beyond
        the most recent swing high (for long) or swing low (for short).
        This confirms that smart money has taken control in the expected direction.

        Returns: dict {detected: bool}
        """
        result = {"detected": False}

        if direction == "neutral" or len(df) < SWING_LOOKBACK + 3:
            return result

        # Reference window: exclude last 2 bars (where BOS is being checked)
        reference = df.iloc[-(SWING_LOOKBACK + 2):-2]
        curr_close = df.iloc[-1]["close"]

        if direction == "long":
            # BOS long: current close breaks above the prior swing high
            prior_high = reference["high"].max()
            if curr_close > prior_high:
                result["detected"] = True

        elif direction == "short":
            # BOS short: current close breaks below the prior swing low
            prior_low = reference["low"].min()
            if curr_close < prior_low:
                result["detected"] = True

        return result