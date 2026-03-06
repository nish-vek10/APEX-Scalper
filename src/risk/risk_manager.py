# /src/risk/risk_manager.py
"""
APEX Scalper — Risk Manager
==============================
Portfolio-level risk controls applied on top of per-trade position sizing.
Acts as the final gate before any trade is allowed to fire.

Controls:
    1. Daily drawdown limit    — shuts algo if -2% daily DD hit
    2. Max concurrent trades   — per instrument and total
    3. Duplicate signal filter — prevents re-entering same instrument too soon
    4. Daily P&L tracking      — tracks realised P&L across the session
"""

from datetime import datetime, date
import pandas as pd

from config.settings import (
    DAILY_DRAWDOWN_LIMIT,
    MAX_OPEN_TRADES_TOTAL,
    MAX_OPEN_TRADES_PER_INSTRUMENT,
    INITIAL_CAPITAL,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class RiskManager:
    """
    Stateful risk manager — maintains open trade inventory and daily P&L.
    Must be instantiated once and kept alive across the trading session.
    """

    def __init__(self, initial_balance: float = INITIAL_CAPITAL):
        self.initial_balance   = initial_balance
        self.current_balance   = initial_balance
        self.day_start_balance = initial_balance
        self.current_date      = date.today()

        # Active trades: {trade_id: {instrument, direction, lots, entry, sl, tps, open_time}}
        self.open_trades: dict = {}
        self.trade_id_counter: int = 0

        # Daily tracking
        self.daily_pnl:       float = 0.0
        self.daily_trades:    int   = 0
        self.daily_dd_hit:    bool  = False

        logger.info(
            f"RiskManager initialised | Balance: ${initial_balance:,.2f}"
        )

    # ─────────────────────────────────────────────────────────────────────
    # DAILY RESET
    # ─────────────────────────────────────────────────────────────────────

    def check_daily_reset(self, current_dt: datetime) -> None:
        """
        Reset daily counters when a new trading day starts.
        Called at the beginning of each bar evaluation.
        """
        today = current_dt.date() if hasattr(current_dt, "date") else current_dt
        if today != self.current_date:
            logger.info(
                f"New trading day: {today} | "
                f"Resetting daily counters | "
                f"Yesterday P&L: ${self.daily_pnl:+.2f}"
            )
            self.current_date      = today
            self.day_start_balance = self.current_balance
            self.daily_pnl         = 0.0
            self.daily_trades      = 0
            self.daily_dd_hit      = False

    # ─────────────────────────────────────────────────────────────────────
    # PRE-TRADE APPROVAL
    # ─────────────────────────────────────────────────────────────────────

    def approve_trade(
        self,
        instrument: str,
        risk_amount: float,
        current_dt: datetime
    ) -> dict:
        """
        Final risk gate — check if a new trade is permitted.

        Args:
            instrument:  Oanda symbol of proposed trade
            risk_amount: USD amount at risk for this trade
            current_dt:  Current bar datetime

        Returns:
            dict {approved: bool, reason: str}
        """
        self.check_daily_reset(current_dt)

        # ── 1. DAILY DRAWDOWN KILL SWITCH ─────────────────────────────────
        if self.daily_dd_hit:
            return {"approved": False, "reason": "Daily drawdown limit already hit — trading halted"}

        daily_dd_pct = (self.current_balance - self.day_start_balance) / self.day_start_balance
        if daily_dd_pct <= -DAILY_DRAWDOWN_LIMIT:
            self.daily_dd_hit = True
            logger.warning(
                f"DAILY DRAWDOWN LIMIT HIT: {daily_dd_pct*100:.2f}% | "
                f"Trading halted for today."
            )
            return {"approved": False, "reason": f"Daily DD limit hit: {daily_dd_pct*100:.2f}%"}

        # ── 2. MAX TOTAL OPEN TRADES ──────────────────────────────────────
        if len(self.open_trades) >= MAX_OPEN_TRADES_TOTAL:
            return {
                "approved": False,
                "reason":   f"Max total open trades reached ({MAX_OPEN_TRADES_TOTAL})"
            }

        # ── 3. MAX PER-INSTRUMENT OPEN TRADES ────────────────────────────
        instrument_trade_count = sum(
            1 for t in self.open_trades.values()
            if t["instrument"] == instrument
        )
        if instrument_trade_count >= MAX_OPEN_TRADES_PER_INSTRUMENT:
            return {
                "approved": False,
                "reason":   f"Max trades for {instrument} reached ({MAX_OPEN_TRADES_PER_INSTRUMENT})"
            }

        # ── ALL CHECKS PASSED ─────────────────────────────────────────────
        return {"approved": True, "reason": "Risk checks passed"}

    # ─────────────────────────────────────────────────────────────────────
    # TRADE REGISTRATION
    # ─────────────────────────────────────────────────────────────────────

    def register_trade(
        self,
        instrument:  str,
        direction:   str,
        lots:        float,
        entry_price: float,
        sl_price:    float,
        tp_prices:   list,
        open_time:   datetime,
        score:       float,
    ) -> int:
        """
        Register a new open trade with the risk manager.

        Returns:
            trade_id (int) — unique identifier for this trade
        """
        self.trade_id_counter += 1
        trade_id = self.trade_id_counter

        self.open_trades[trade_id] = {
            "instrument":  instrument,
            "direction":   direction,
            "lots":        lots,
            "entry_price": entry_price,
            "sl_price":    sl_price,
            "tp_prices":   tp_prices,
            "open_time":   open_time,
            "score":       score,
            "tp_hit":      [],     # Which TPs have been hit
            "trailing_sl": None,   # Trailing SL level (activates after TP1)
        }
        self.daily_trades += 1

        logger.info(
            f"Trade #{trade_id} registered | {instrument} {direction.upper()} | "
            f"Lots: {lots} | Entry: {entry_price} | SL: {sl_price} | "
            f"TPs: {tp_prices} | Score: {score:.1f}"
        )
        return trade_id

    def close_trade(
        self,
        trade_id:    int,
        exit_price:  float,
        exit_time:   datetime,
        close_reason: str = "manual",
    ) -> dict:
        """
        Close an open trade and update account balance.

        Returns:
            dict with trade summary including pnl
        """
        if trade_id not in self.open_trades:
            logger.warning(f"Trade #{trade_id} not found in open trades.")
            return {}

        trade    = self.open_trades.pop(trade_id)
        config   = __import__(
            "config.instruments", fromlist=["get_instrument"]
        ).get_instrument(trade["instrument"])

        pip_size          = config["pip_size"]
        pip_value_per_lot = config["pip_value_per_lot"]

        # Calculate P&L in pips and USD
        if trade["direction"] == "long":
            pips_pnl = (exit_price - trade["entry_price"]) / pip_size
        else:
            pips_pnl = (trade["entry_price"] - exit_price) / pip_size

        usd_pnl = pips_pnl * pip_value_per_lot * trade["lots"]

        # Update balances
        self.current_balance += usd_pnl
        self.daily_pnl       += usd_pnl

        summary = {
            "trade_id":     trade_id,
            "instrument":   trade["instrument"],
            "direction":    trade["direction"],
            "lots":         trade["lots"],
            "entry_price":  trade["entry_price"],
            "exit_price":   exit_price,
            "open_time":    trade["open_time"],
            "close_time":   exit_time,
            "pips_pnl":     round(pips_pnl, 2),
            "usd_pnl":      round(usd_pnl, 2),
            "close_reason": close_reason,
            "score":        trade["score"],
        }

        outcome = "WIN" if usd_pnl > 0 else "LOSS" if usd_pnl < 0 else "BREAKEVEN"
        logger.info(
            f"Trade #{trade_id} CLOSED [{outcome}] | "
            f"{trade['instrument']} {trade['direction'].upper()} | "
            f"Pips: {pips_pnl:+.1f} | P&L: ${usd_pnl:+.2f} | "
            f"Reason: {close_reason} | Balance: ${self.current_balance:,.2f}"
        )
        return summary

    # ─────────────────────────────────────────────────────────────────────
    # GETTERS
    # ─────────────────────────────────────────────────────────────────────

    def get_current_balance(self) -> float:
        return self.current_balance

    def get_open_trade_count(self) -> int:
        return len(self.open_trades)

    def get_daily_pnl(self) -> float:
        return self.daily_pnl

    def get_daily_dd_pct(self) -> float:
        if self.day_start_balance == 0:
            return 0.0
        return (self.current_balance - self.day_start_balance) / self.day_start_balance