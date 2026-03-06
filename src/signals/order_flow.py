# /src/signals/order_flow.py
"""
APEX Scalper — Signal Module C: Order Flow Proxy
==================================================
Infers order flow activity from bar characteristics since true Level 2
order book data is unavailable through Oanda's CFD feed.

Proxies used:
    Volume proxy:   (high - low) / ATR — relative bar range as activity gauge
    Spread proxy:   close position within bar (high close = buying pressure)
    Velocity:       rate of price movement across last 3 bars
Maximum score: 2.0 points.

Scoring breakdown:
    Volume spike > 1.5x 20-bar average  → 1.0 pt
    Bar close in upper/lower third       → 0.5 pt  (buying/selling pressure)
    Price velocity acceleration          → 0.5 pt
"""

import pandas as pd
import numpy as np

from config.settings import VOLUME_LOOKBACK
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Volume spike threshold — ratio of current vol_proxy vs rolling average
VOLUME_SPIKE_THRESHOLD = 1.5


class OrderFlowSignal:
    """
    Module C — Order flow proxy signal evaluator.
    Operates on the M5 entry timeframe.
    Infers directional pressure from bar structure and range activity.
    """

    def evaluate(self, df_m5: pd.DataFrame) -> dict:
        """
        Evaluate order flow proxy signals on the current M5 bar.

        Args:
            df_m5: M5 DataFrame with indicators, up to and including current bar.

        Returns:
            dict with keys:
                direction       (str)   — "long" | "short" | "neutral"
                score           (float) — 0.0–2.0
                vol_spike       (bool)  — volume proxy spike detected
                bar_pressure    (str)   — "buying" | "selling" | "neutral"
                velocity_ok     (bool)  — price velocity acceleration confirmed
                vol_ratio       (float) — current bar's volume ratio vs average
                detail          (str)   — Human-readable breakdown
        """
        result = {
            "direction":    "neutral",
            "score":        0.0,
            "vol_spike":    False,
            "bar_pressure": "neutral",
            "velocity_ok":  False,
            "vol_ratio":    0.0,
            "detail":       "",
        }

        if len(df_m5) < VOLUME_LOOKBACK + 3:
            result["detail"] = "Insufficient bars for order flow check"
            return result

        curr = df_m5.iloc[-1]

        open_price  = curr.get("open")
        high_price  = curr.get("high")
        low_price   = curr.get("low")
        close_price = curr.get("close")
        vol_ratio   = curr.get("vol_ratio")

        if any(pd.isna(v) for v in [open_price, high_price, low_price, close_price]):
            result["detail"] = "OHLC values unavailable"
            return result

        result["vol_ratio"] = vol_ratio if not pd.isna(vol_ratio) else 0.0

        # ── 1. VOLUME SPIKE DETECTION (1.0 pt) ───────────────────────────
        vol_score = 0.0
        if not pd.isna(vol_ratio) and vol_ratio >= VOLUME_SPIKE_THRESHOLD:
            vol_score = 1.0
            result["vol_spike"] = True

        # ── 2. BAR CLOSE PRESSURE (0.5 pt) ───────────────────────────────
        # Where the bar closed relative to its range tells us buyer/seller dominance
        bar_range = high_price - low_price
        pressure_score = 0.0
        pressure = "neutral"

        if bar_range > 0:
            # Normalised close position: 0 = bottom of bar, 1 = top of bar
            close_position = (close_price - low_price) / bar_range

            if close_position >= 0.67:
                # Close in upper third → buying pressure
                pressure = "buying"
                pressure_score = 0.5
            elif close_position <= 0.33:
                # Close in lower third → selling pressure
                pressure = "selling"
                pressure_score = 0.5

        result["bar_pressure"] = pressure

        # ── 3. PRICE VELOCITY (0.5 pt) ────────────────────────────────────
        # Compare average bar move over last 3 bars vs 10-bar average
        # Acceleration in price movement signals momentum-driven order flow
        velocity_score = 0.0
        recent_3  = df_m5.tail(3)
        recent_10 = df_m5.tail(10)

        move_3  = abs(recent_3["close"].iloc[-1]  - recent_3["close"].iloc[0])
        move_10 = abs(recent_10["close"].iloc[-1] - recent_10["close"].iloc[0])

        # Velocity = recent 3-bar move is more than 40% of 10-bar move
        if move_10 > 0 and (move_3 / move_10) > 0.40:
            velocity_score = 0.5
            result["velocity_ok"] = True

        # ── DIRECTION FROM BAR PRESSURE + VELOCITY ────────────────────────
        # Volume spike confirms activity; pressure and velocity give direction
        if pressure == "buying":
            direction = "long"
        elif pressure == "selling":
            direction = "short"
        else:
            # If no pressure signal, fall back to last 3-bar price direction
            if len(df_m5) >= 3:
                price_delta = df_m5["close"].iloc[-1] - df_m5["close"].iloc[-3]
                direction = "long" if price_delta > 0 else "short" if price_delta < 0 else "neutral"
            else:
                direction = "neutral"

        total_score = vol_score + pressure_score + velocity_score

        # Only emit a signal if volume spike is present — otherwise noise
        if not result["vol_spike"]:
            direction = "neutral"
            total_score = 0.0

        result["direction"] = direction
        result["score"]     = round(min(total_score, 2.0), 2)
        result["detail"]    = (
            f"OrderFlow [{direction.upper()}] | "
            f"VolRatio: {result['vol_ratio']:.2f}x ({vol_score:.1f}pt) | "
            f"Pressure: {pressure} ({pressure_score:.1f}pt) | "
            f"Velocity: {result['velocity_ok']} ({velocity_score:.1f}pt) | "
            f"Total: {result['score']}/2.0"
        )
        return result