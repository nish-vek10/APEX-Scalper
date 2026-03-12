# /src/risk/position_sizer.py
"""
APEX Scalper — Position Sizer
================================
Calculates position size (in lots) for each trade using
ATR-based stop loss distance and account balance risk percentage.

Formula:
    Risk Amount = Account Balance × Risk %
    SL Distance = ATR × SL_ATR_MULTIPLIER  (in price units)
    SL in Pips  = SL Distance / Pip Size
    Lot Size    = Risk Amount / (SL in Pips × Pip Value per Lot)

Position size is then adjusted by:
    - Signal score tier multiplier (0.5x / 0.75x / 1.0x)
    - Clipped to instrument min/max lot sizes
    - Rounded to instrument's lot step
"""

import math
import pandas as pd

from config.settings import (
    BASE_RISK_PCT,
    MAX_RISK_PCT,
    SL_ATR_MULTIPLIER,
    TP_TIERS,
    SLIPPAGE_PIPS,
    RISK_MODE,                  # "static" | "dynamic" — controls lot sizing reference
    INITIAL_CAPITAL,            # Used as fixed reference balance in static mode
    MAX_LOTS_PER_INSTRUMENT,    # Per-instrument hard lot cap
)

from config.instruments import get_instrument
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PositionSizer:
    """
    Computes trade parameters: lot size, SL price, and TP price levels.
    """

    def calculate(
        self,
        instrument:    str,
        direction:     str,        # "long" | "short"
        entry_price:   float,
        atr:           float,
        account_balance: float,
        size_multiplier: float,    # From scorer's tier (0.5 / 0.75 / 1.0)
    ) -> dict:
        """
        Compute lot size and trade levels for a given signal.

        Args:
            instrument:      Oanda symbol e.g. "XAU_USD"
            direction:       Trade direction "long" | "short"
            entry_price:     Current market price (with simulated slippage applied)
            atr:             Current ATR value in price units
            account_balance: Current account balance in account currency (USD)
            size_multiplier: Score-based multiplier from ConflueceScorer

        Returns:
            dict with keys:
                lots         (float)  — position size in lots
                sl_price     (float)  — stop loss price level
                tp_prices    (list)   — [tp1, tp2, tp3] price levels
                sl_pips      (float)  — stop distance in pips
                risk_amount  (float)  — USD amount at risk
                valid        (bool)   — False if sizing failed
                reason       (str)    — error message if not valid
        """
        result = {
            "lots":       0.0,
            "sl_price":   0.0,
            "tp_prices":  [],
            "sl_pips":    0.0,
            "risk_amount":0.0,
            "valid":      False,
            "reason":     "",
        }

        config = get_instrument(instrument)
        pip_size         = config["pip_size"]
        pip_value_per_lot= config["pip_value_per_lot"]
        min_lot          = config["min_lot"]
        max_lot          = config["max_lot"]
        lot_step         = config["lot_step"]

        # ── 1. CALCULATE STOP LOSS DISTANCE ──────────────────────────────
        sl_distance = atr * SL_ATR_MULTIPLIER       # Price units
        sl_pips     = sl_distance / pip_size         # Convert to pips

        if sl_pips <= 0:
            result["reason"] = "SL distance is zero or negative — ATR may be invalid"
            return result

        # ── 2. CALCULATE RISK AMOUNT ──────────────────────────────────────
        """
        Static mode  → always size off INITIAL_CAPITAL ($10,000 fixed).
                       Lot sizes remain constant regardless of account growth.
                       Conservative — prevents runaway sizing on winning streaks.
        Dynamic mode → size off current live equity (account_balance).
                       Lot sizes compound as the account grows or shrinks.
                       Aggressive — higher upside ceiling, higher drawdown risk.
        """

        if RISK_MODE == "static":
            reference_balance = INITIAL_CAPITAL  # Fixed $10k throughout backtest
        else:
            reference_balance = account_balance  # Live equity at trade entry

        effective_risk_pct = BASE_RISK_PCT * size_multiplier
        effective_risk_pct = min(effective_risk_pct, MAX_RISK_PCT)  # Hard cap
        risk_amount = reference_balance * effective_risk_pct

        # ── 3. CALCULATE LOT SIZE ─────────────────────────────────────────
        # Adjust sl_pips for slippage
        adjusted_sl_pips = sl_pips + SLIPPAGE_PIPS
        lot_size = risk_amount / (adjusted_sl_pips * pip_value_per_lot)

        # ── 4. CLIP AND ROUND TO VALID LOT SIZE ──────────────────────────
        lot_size = min(lot_size, max_lot)  # Apply broker max first
        lot_size = self._round_to_step(lot_size, lot_step)

        # Apply per-instrument hard lot cap (safety ceiling defined in settings)
        instrument_cap = MAX_LOTS_PER_INSTRUMENT.get(instrument)
        if instrument_cap:
            lot_size = min(lot_size, instrument_cap)

        # ── RISK GUARD: reject trade if min_lot would breach MAX_RISK_PCT ──
        # This prevents silent lot inflation when the calculated size is below
        # the broker's minimum — common on indices (US30, NAS100) at small
        # account sizes where 1 lot already risks far more than intended.
        if lot_size < min_lot:
            # Check what the actual dollar risk would be at min_lot
            min_lot_risk = min_lot * adjusted_sl_pips * pip_value_per_lot
            max_allowed_risk = reference_balance * MAX_RISK_PCT

            if min_lot_risk > max_allowed_risk * 1.5:  # 50% tolerance buffer
                result["reason"] = (
                    f"Min lot risk ${min_lot_risk:.2f} exceeds max allowed "
                    f"${max_allowed_risk:.2f} — trade skipped to protect capital"
                )
                logger.debug(
                    f"[{instrument}] Trade skipped — min lot risk "
                    f"${min_lot_risk:.2f} > max allowed ${max_allowed_risk:.2f}"
                )
                return result

            # Within tolerance — use min_lot and accept slightly elevated risk
            lot_size = min_lot

        if lot_size <= 0:
            result["reason"] = "Calculated lot size is zero after rounding"
            return result

        # ── 5. STOP LOSS PRICE ────────────────────────────────────────────
        if direction == "long":
            sl_price  = entry_price - sl_distance
        else:
            sl_price  = entry_price + sl_distance

        # ── 6. TAKE PROFIT LEVELS ─────────────────────────────────────────
        tp_prices = []
        for tp_tier in TP_TIERS:
            rr         = tp_tier["rr"]
            tp_distance = sl_distance * rr
            if direction == "long":
                tp_price = entry_price + tp_distance
            else:
                tp_price = entry_price - tp_distance
            tp_prices.append(round(tp_price, config["digits"] + 1))

        # ── 7. VERIFY ACTUAL RISK AMOUNT ──────────────────────────────────
        actual_risk = lot_size * adjusted_sl_pips * pip_value_per_lot

        result.update({
            "lots":        lot_size,
            "sl_price":    round(sl_price, config["digits"] + 1),
            "tp_prices":   tp_prices,
            "sl_pips":     round(sl_pips, 1),
            "risk_amount": round(actual_risk, 2),
            "valid":       True,
            "reason":      "OK",
        })

        logger.debug(
            f"[{RISK_MODE.upper()}] {instrument} {direction.upper()} | "
            f"Ref: ${reference_balance:,.0f} | Lots: {lot_size} | "
            f"SL: {sl_pips:.1f} pips | Risk: ${actual_risk:.2f} "
            f"({effective_risk_pct * 100:.3f}%) | TPs: {tp_prices}"
        )
        return result

    # ─────────────────────────────────────────────────────────────────────
    # HELPER
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _round_to_step(value: float, step: float) -> float:
        """Round a value down to the nearest valid lot step increment."""
        if step <= 0:
            return value
        factor = 1.0 / step
        return math.floor(value * factor) / factor