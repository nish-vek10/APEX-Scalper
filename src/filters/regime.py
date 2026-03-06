# /src/filters/regime.py
"""
APEX Scalper — Regime Filter
===============================
The gatekeeper layer. Every bar evaluation passes through this filter first.
If ANY regime condition fails, no signal modules are evaluated — the algo waits.

Regime checks performed:
    1. Session gate       — is this instrument within its active trading hours?
    2. Volatility gate    — is ATR within healthy bounds (not flat, not spiking)?
    3. Spread gate        — is current spread acceptable?
    4. ADX regime         — trending vs ranging (used to weight signal modules)
"""

from datetime import datetime, time
import pytz
import pandas as pd

from config.settings import (
    ADX_TREND_THRESHOLD,
    ATR_FLOOR_MULTIPLIER,
    ATR_CEILING_MULTIPLIER,
    MAX_SPREAD_MULTIPLIER,
)
from config.instruments import get_instrument
from src.utils.logger import get_logger

logger = get_logger(__name__)

UTC = pytz.utc


class RegimeFilter:
    """
    Evaluates market regime conditions for a given instrument and bar timestamp.
    Returns a RegimeResult indicating whether trading is permitted,
    and the detected regime type (trending vs ranging).
    """

    def evaluate(
        self,
        instrument: str,
        df_m5: pd.DataFrame,
        df_m15: pd.DataFrame,
        current_time: datetime,
        current_spread: float = None
    ) -> dict:
        """
        Run all regime checks for the current bar.

        Args:
            instrument:     Oanda symbol e.g. "XAU_USD"
            df_m5:          M5 DataFrame (with indicators) up to current bar
            df_m15:         M15 DataFrame (with indicators) up to current bar
            current_time:   UTC datetime of the current bar
            current_spread: Current bid/ask spread (optional — for live mode)

        Returns:
            dict with keys:
                tradeable  (bool)  — True if all checks pass
                regime     (str)   — "trending" | "ranging" | "blocked"
                reason     (str)   — human-readable reason if not tradeable
                adx        (float) — current ADX value
                atr        (float) — current ATR value
        """
        config = get_instrument(instrument)
        result = {
            "tradeable": False,
            "regime":    "blocked",
            "reason":    "",
            "adx":       None,
            "atr":       None,
        }

        # Guard: need at least 1 row of data
        if df_m5.empty or df_m15.empty:
            result["reason"] = "Insufficient data"
            return result

        bar_m5  = df_m5.iloc[-1]
        bar_m15 = df_m15.iloc[-1]

        # ── 1. SESSION GATE ───────────────────────────────────────────────
        if not self._is_active_session(config, current_time):
            result["reason"] = f"Outside active session for {instrument}"
            return result

        # ── 2. ATR VOLATILITY GATE ────────────────────────────────────────
        atr_current = bar_m5.get("atr")
        if pd.isna(atr_current) or atr_current <= 0:
            result["reason"] = "ATR unavailable or zero"
            return result

        # Compute ATR 20-bar rolling average for floor/ceiling comparison
        atr_avg = df_m5["atr"].rolling(20).mean().iloc[-1]

        atr_floor   = atr_avg * ATR_FLOOR_MULTIPLIER
        atr_ceiling = atr_avg * ATR_CEILING_MULTIPLIER

        if atr_current < atr_floor:
            result["reason"] = f"ATR too low (flat market) — {atr_current:.5f} < floor {atr_floor:.5f}"
            result["atr"] = atr_current
            return result

        if atr_current > atr_ceiling:
            result["reason"] = f"ATR too high (news spike) — {atr_current:.5f} > ceiling {atr_ceiling:.5f}"
            result["atr"] = atr_current
            return result

        # ── 3. SPREAD GATE ────────────────────────────────────────────────
        typical_spread = config["typical_spread"]
        if current_spread is not None:
            max_spread = typical_spread * MAX_SPREAD_MULTIPLIER
            if current_spread > max_spread:
                result["reason"] = f"Spread too wide — {current_spread:.4f} > max {max_spread:.4f}"
                result["atr"] = atr_current
                return result

        # ── 4. ADX REGIME DETECTION ───────────────────────────────────────
        adx_value = bar_m15.get("adx")
        result["atr"] = atr_current
        result["adx"] = adx_value if not pd.isna(adx_value) else None

        # Determine regime type — used by scorer to weight signal modules
        if pd.isna(adx_value):
            regime = "ranging"    # Default to ranging if ADX unavailable
        elif adx_value >= ADX_TREND_THRESHOLD:
            regime = "trending"
        else:
            regime = "ranging"

        # ── ALL CHECKS PASSED ─────────────────────────────────────────────
        result["tradeable"] = True
        result["regime"]    = regime
        result["reason"]    = f"OK — {regime} | ADX: {f'{adx_value:.1f}' if adx_value else 'N/A'}"
        return result

    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE HELPERS
    # ─────────────────────────────────────────────────────────────────────

    def _is_active_session(self, config: dict, current_time: datetime) -> bool:
        """
        Check if the current UTC time falls within the instrument's active session.

        Args:
            config:       Instrument config dict from instruments.py
            current_time: Current bar datetime (timezone-aware UTC)

        Returns:
            True if within active session window.
        """
        sessions = config.get("sessions", {})
        active   = sessions.get("active")

        if active is None:
            return True  # No session restriction defined → always active

        # Ensure timezone-aware comparison
        if current_time.tzinfo is None:
            current_time = UTC.localize(current_time)

        open_str, close_str = active
        open_h,  open_m  = map(int, open_str.split(":"))
        close_h, close_m = map(int, close_str.split(":"))

        session_open  = current_time.replace(hour=open_h,  minute=open_m,  second=0, microsecond=0)
        session_close = current_time.replace(hour=close_h, minute=close_m, second=0, microsecond=0)

        return session_open <= current_time <= session_close