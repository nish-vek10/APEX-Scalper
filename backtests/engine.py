# /backtests/engine.py
"""
APEX Scalper — Backtest Engine
================================
Simulates the APEX Scalper strategy on historical Oanda data.
Iterates bar-by-bar through M5 candles, evaluating the full
signal pipeline on each bar exactly as it would run live.

Anti-lookahead: at bar index i, only df.iloc[:i+1] is visible.

Output:
    - Trade log (list of dicts)
    - Equity curve (pd.Series)
    - Performance metrics (dict)
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional

from config.settings import (
    BACKTEST_START, BACKTEST_END,
    INITIAL_CAPITAL, COMMISSION_PER_LOT, SLIPPAGE_PIPS,
    TP_TIERS, TRAILING_STOP_ATR_MULTIPLIER,
    MIN_SCORE_TO_TRADE,
)
from config.instruments import get_instrument, get_all_oanda_symbols
from src.data.oanda_client import OandaClient
from src.data.market_data import MarketData
from src.filters.regime import RegimeFilter
from src.filters.htf_bias import HTFBias
from src.signals.momentum import MomentumSignal
from src.signals.mean_reversion import MeanReversionSignal
from src.signals.order_flow import OrderFlowSignal
from src.signals.smc import SMCSignal
from src.signals.scorer import ConflueceScorer, SignalResult
from src.risk.position_sizer import PositionSizer
from src.risk.risk_manager import RiskManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BacktestEngine:
    """
    Event-driven bar-by-bar backtest engine for APEX Scalper.
    Runs one instrument at a time for clean isolation,
    then aggregates results across all instruments at the end.
    """

    def __init__(self):
        # Instantiate all strategy components once
        self.regime_filter  = RegimeFilter()
        self.htf_bias       = HTFBias()
        self.momentum       = MomentumSignal()
        self.mean_reversion = MeanReversionSignal()
        self.order_flow     = OrderFlowSignal()
        self.smc            = SMCSignal()
        self.scorer         = ConflueceScorer()
        self.position_sizer = PositionSizer()
        self.risk_manager   = RiskManager(initial_balance=INITIAL_CAPITAL)

        # Results storage
        self.all_trades:    list         = []
        self.equity_curve:  list         = []
        self.bar_log:       list         = []

    # ─────────────────────────────────────────────────────────────────────
    # MAIN ENTRY POINT
    # ─────────────────────────────────────────────────────────────────────

    def run(
        self,
        instruments: list = None,
        from_date: str    = BACKTEST_START,
        to_date: str      = BACKTEST_END,
    ) -> dict:
        """
        Execute the full backtest across all specified instruments.

        Args:
            instruments: List of Oanda symbols. Defaults to all configured.
            from_date:   Backtest start "YYYY-MM-DD"
            to_date:     Backtest end "YYYY-MM-DD"

        Returns:
            dict with keys: trades, equity_curve, metrics, summary
        """
        if instruments is None:
            instruments = get_all_oanda_symbols()

        logger.info(
            f"\n"
            f"╔══════════════════════════════════════════╗\n"
            f"║       APEX SCALPER BACKTEST START        ║\n"
            f"╚══════════════════════════════════════════╝\n"
            f"  Period:      {from_date} → {to_date}\n"
            f"  Instruments: {instruments}\n"
            f"  Capital:     ${INITIAL_CAPITAL:,.2f}"
        )

        # Fetch all historical data via Oanda
        oanda_client = OandaClient()
        market_data  = MarketData(oanda_client)

        for instrument in instruments:
            logger.info(f"Loading data for {instrument}...")
            try:
                market_data.load_instrument(
                    instrument=instrument,
                    from_date=from_date,
                    to_date=to_date
                )
            except Exception as e:
                logger.error(f"Failed to load {instrument}: {e}")
                continue

        # Run backtest per instrument
        for instrument in instruments:
            df_m5  = market_data.get(instrument, "M5")
            df_m15 = market_data.get(instrument, "M15")
            df_h1  = market_data.get(instrument, "H1")

            if df_m5.empty:
                logger.warning(f"No M5 data for {instrument} — skipping.")
                continue

            logger.info(f"Running backtest for {instrument} | {len(df_m5)} M5 bars...")
            self._run_instrument(instrument, df_m5, df_m15, df_h1)

        # Final forced-close of any remaining open trades at last bar
        self._close_all_open_positions(force=True)

        # Compute aggregate performance metrics
        metrics = self._compute_metrics()

        logger.info(
            f"\n╔══════════════════════════════════════════╗\n"
            f"║       APEX SCALPER BACKTEST COMPLETE     ║\n"
            f"╚══════════════════════════════════════════╝\n"
            f"  Total Trades: {metrics.get('total_trades', 0)}\n"
            f"  Win Rate:     {metrics.get('win_rate_pct', 0):.1f}%\n"
            f"  Net P&L:      ${metrics.get('net_pnl', 0):+,.2f}\n"
            f"  Max Drawdown: {metrics.get('max_drawdown_pct', 0):.2f}%\n"
            f"  Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}"
        )

        return {
            "trades":       self.all_trades,
            "equity_curve": pd.Series(
                [e["equity"] for e in self.equity_curve],
                index=[e["time"] for e in self.equity_curve],
                name="equity"
            ),
            "metrics":      metrics,
            "bar_log":      self.bar_log,
        }

    # ─────────────────────────────────────────────────────────────────────
    # PER-INSTRUMENT BACKTEST LOOP
    # ─────────────────────────────────────────────────────────────────────

    def _run_instrument(
        self,
        instrument: str,
        df_m5:  pd.DataFrame,
        df_m15: pd.DataFrame,
        df_h1:  pd.DataFrame,
    ) -> None:
        """
        Bar-by-bar simulation for a single instrument.
        Manages open simulated positions with TP laddering and trailing SL.
        """
        # Simulated open positions for this instrument
        # {trade_id: {entry, sl, tp_prices, direction, lots, atr_at_entry, tp_hit_count}}
        open_positions: dict = {}

        # Warmup: skip first 200 bars to ensure indicator stability
        WARMUP_BARS = 200

        for i in range(WARMUP_BARS, len(df_m5)):
            # ── Anti-lookahead: slice data to current bar ─────────────────
            curr_m5  = df_m5.iloc[:i+1]
            curr_bar = df_m5.iloc[i]
            bar_time = curr_bar.name    # Datetime index

            # Align M15 and H1 to the same timestamp (bars up to current time)
            curr_m15 = df_m15[df_m15.index <= bar_time]
            curr_h1  = df_h1[df_h1.index  <= bar_time]

            if curr_m15.empty or curr_h1.empty:
                continue

            # ── Log equity at each bar ────────────────────────────────────
            self.equity_curve.append({
                "time":   bar_time,
                "equity": self.risk_manager.get_current_balance(),
            })

            # ── 1. CHECK EXISTING POSITIONS ───────────────────────────────
            closed_ids = []
            for tid, pos in open_positions.items():
                close_result = self._check_position_exit(pos, curr_bar, bar_time)
                if close_result["closed"]:
                    trade_summary = self.risk_manager.close_trade(
                        trade_id=tid,
                        exit_price=close_result["exit_price"],
                        exit_time=bar_time,
                        close_reason=close_result["reason"],
                    )
                    # Deduct commission
                    commission = COMMISSION_PER_LOT * pos["lots"]
                    self.risk_manager.current_balance -= commission
                    trade_summary["commission"] = commission
                    trade_summary["net_pnl"] = trade_summary["usd_pnl"] - commission
                    self.all_trades.append(trade_summary)
                    closed_ids.append(tid)

                else:
                    # Update trailing stop if TP1 was hit
                    if len(pos["tp_hit"]) >= 1 and pos["trailing_sl"] is None:
                        atr = curr_bar.get("atr", pos["atr_at_entry"])
                        if not pd.isna(atr):
                            if pos["direction"] == "long":
                                pos["trailing_sl"] = curr_bar["close"] - (atr * TRAILING_STOP_ATR_MULTIPLIER)
                            else:
                                pos["trailing_sl"] = curr_bar["close"] + (atr * TRAILING_STOP_ATR_MULTIPLIER)
                    elif pos["trailing_sl"] is not None:
                        # Trail the stop
                        atr = curr_bar.get("atr", pos["atr_at_entry"])
                        if not pd.isna(atr):
                            if pos["direction"] == "long":
                                new_trail = curr_bar["close"] - (atr * TRAILING_STOP_ATR_MULTIPLIER)
                                pos["trailing_sl"] = max(pos["trailing_sl"], new_trail)
                            else:
                                new_trail = curr_bar["close"] + (atr * TRAILING_STOP_ATR_MULTIPLIER)
                                pos["trailing_sl"] = min(pos["trailing_sl"], new_trail)

            for tid in closed_ids:
                del open_positions[tid]

            # ── 2. REGIME FILTER ──────────────────────────────────────────
            regime_result = self.regime_filter.evaluate(
                instrument=instrument,
                df_m5=curr_m5,
                df_m15=curr_m15,
                current_time=bar_time,
            )

            if not regime_result["tradeable"]:
                continue

            # ── 3. HTF BIAS ───────────────────────────────────────────────
            htf_result = self.htf_bias.evaluate(curr_m15, curr_h1, curr_m5)

            # ── 4. SIGNAL MODULES ─────────────────────────────────────────
            mom_result  = self.momentum.evaluate(curr_m5)
            mr_result   = self.mean_reversion.evaluate(curr_m5)
            of_result   = self.order_flow.evaluate(curr_m5)
            smc_result  = self.smc.evaluate(curr_m5, curr_m15)

            # ── 5. CONFLUENCE SCORER ──────────────────────────────────────
            signal = self.scorer.evaluate(
                instrument=instrument,
                timestamp=bar_time,
                momentum_result=mom_result,
                mean_rev_result=mr_result,
                order_flow_result=of_result,
                smc_result=smc_result,
                htf_result=htf_result,
                regime=regime_result["regime"],
            )

            if not signal.tradeable:
                continue

            # ── 6. RISK APPROVAL ──────────────────────────────────────────
            # Estimate risk amount for pre-approval check
            atr          = curr_bar.get("atr", 0)
            config       = get_instrument(instrument)
            risk_estimate= self.risk_manager.get_current_balance() * 0.005   # rough

            approval = self.risk_manager.approve_trade(
                instrument=instrument,
                risk_amount=risk_estimate,
                current_dt=bar_time,
            )

            if not approval["approved"]:
                logger.debug(f"Trade blocked: {approval['reason']}")
                continue

            # ── 7. POSITION SIZING ────────────────────────────────────────
            # Simulate market entry with slippage
            entry_price = self._apply_slippage(
                curr_bar["close"], signal.direction,
                config["pip_size"]
            )

            sizing = self.position_sizer.calculate(
                instrument=instrument,
                direction=signal.direction,
                entry_price=entry_price,
                atr=atr,
                account_balance=self.risk_manager.get_current_balance(),
                size_multiplier=signal.size_mult,
            )

            if not sizing["valid"]:
                logger.debug(f"Sizing failed: {sizing['reason']}")
                continue

            # ── 8. REGISTER TRADE ─────────────────────────────────────────
            trade_id = self.risk_manager.register_trade(
                instrument=instrument,
                direction=signal.direction,
                lots=sizing["lots"],
                entry_price=entry_price,
                sl_price=sizing["sl_price"],
                tp_prices=sizing["tp_prices"],
                open_time=bar_time,
                score=signal.score,
            )

            # Add to local position tracker with TP management state
            open_positions[trade_id] = {
                "instrument":    instrument,
                "direction":     signal.direction,
                "lots":          sizing["lots"],
                "entry_price":   entry_price,
                "sl_price":      sizing["sl_price"],
                "tp_prices":     sizing["tp_prices"],
                "open_time":     bar_time,
                "score":         signal.score,
                "atr_at_entry":  atr,
                "tp_hit":        [],
                "remaining_lots":sizing["lots"],
                "trailing_sl":   None,
            }

            # Log bar event
            self.bar_log.append({
                "time":       bar_time,
                "instrument": instrument,
                "event":      "ENTRY",
                "direction":  signal.direction,
                "score":      signal.score,
                "entry":      entry_price,
                "sl":         sizing["sl_price"],
                "regime":     regime_result["regime"],
            })

    # ─────────────────────────────────────────────────────────────────────
    # POSITION EXIT LOGIC
    # ─────────────────────────────────────────────────────────────────────

    def _check_position_exit(self, pos: dict, bar: pd.Series, bar_time) -> dict:
        """
        Check if an open position should be closed or partially closed on this bar.
        Evaluates SL, trailing SL, and TP levels using bar OHLC.

        Returns:
            dict {closed: bool, exit_price: float, reason: str}
        """
        direction = pos["direction"]
        high  = bar["high"]
        low   = bar["low"]
        close = bar["close"]

        # Determine effective SL (use trailing if active, else original)
        effective_sl = pos["trailing_sl"] if pos["trailing_sl"] is not None else pos["sl_price"]

        # ── STOP LOSS HIT ─────────────────────────────────────────────────
        if direction == "long" and low <= effective_sl:
            return {"closed": True, "exit_price": effective_sl, "reason": "stop_loss"}
        if direction == "short" and high >= effective_sl:
            return {"closed": True, "exit_price": effective_sl, "reason": "stop_loss"}

        # ── TAKE PROFIT LEVELS ─────────────────────────────────────────────
        for idx, tp_price in enumerate(pos["tp_prices"]):
            if idx in pos["tp_hit"]:
                continue   # Already hit this TP

            tp_hit = False
            if direction == "long"  and high >= tp_price:
                tp_hit = True
            elif direction == "short" and low <= tp_price:
                tp_hit = True

            if tp_hit:
                pos["tp_hit"].append(idx)
                tp_tier  = TP_TIERS[idx]
                close_pct = tp_tier["close_pct"]

                # If this is the last TP tier — fully close
                if idx == len(pos["tp_prices"]) - 1 or len(pos["tp_hit"]) == len(pos["tp_prices"]):
                    return {"closed": True, "exit_price": tp_price, "reason": f"tp{idx+1}"}

                # Partial close — update remaining lots (simplified: track fully for P&L)
                # In full implementation this would reduce position partially
                # For backtest simplicity, we treat last TP as the exit
                break

        return {"closed": False, "exit_price": None, "reason": None}

    # ─────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────

    def _apply_slippage(self, price: float, direction: str, pip_size: float) -> float:
        """Simulate entry slippage — add to long entry, subtract from short."""
        slip = SLIPPAGE_PIPS * pip_size
        if direction == "long":
            return price + slip
        return price - slip

    def _close_all_open_positions(self, force: bool = False) -> None:
        """Force-close all simulated open positions at end of backtest."""
        for tid in list(self.risk_manager.open_trades.keys()):
            logger.debug(f"Force-closing trade #{tid} at backtest end.")
            self.risk_manager.close_trade(
                trade_id=tid,
                exit_price=0.0,   # Will be overridden by last bar close in real impl
                exit_time=datetime.utcnow(),
                close_reason="backtest_end",
            )

    # ─────────────────────────────────────────────────────────────────────
    # PERFORMANCE METRICS
    # ─────────────────────────────────────────────────────────────────────

    def _compute_metrics(self) -> dict:
        """
        Compute comprehensive performance metrics from the trade log
        and equity curve for report generation.

        Returns:
            dict containing all performance statistics.
        """
        if not self.all_trades:
            return {"total_trades": 0}

        trades_df = pd.DataFrame(self.all_trades)

        # Ensure net_pnl column exists
        if "net_pnl" not in trades_df.columns:
            trades_df["net_pnl"] = trades_df.get("usd_pnl", 0) - trades_df.get("commission", 0)

        total_trades = len(trades_df)
        winners      = trades_df[trades_df["net_pnl"] > 0]
        losers       = trades_df[trades_df["net_pnl"] < 0]
        breakevens   = trades_df[trades_df["net_pnl"] == 0]

        win_count  = len(winners)
        loss_count = len(losers)
        win_rate   = win_count / total_trades if total_trades > 0 else 0

        gross_profit = winners["net_pnl"].sum() if len(winners) > 0 else 0
        gross_loss   = abs(losers["net_pnl"].sum()) if len(losers) > 0 else 0
        net_pnl      = trades_df["net_pnl"].sum()

        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        avg_win  = winners["net_pnl"].mean() if len(winners) > 0 else 0
        avg_loss = losers["net_pnl"].mean()  if len(losers)  > 0 else 0
        avg_rr   = abs(avg_win / avg_loss)   if avg_loss != 0 else 0

        # ── EQUITY CURVE METRICS ──────────────────────────────────────────
        eq_series = pd.Series(
            [INITIAL_CAPITAL] + [INITIAL_CAPITAL + trades_df["net_pnl"].iloc[:i+1].sum()
                                  for i in range(len(trades_df))]
        )

        # Max drawdown
        rolling_max = eq_series.cummax()
        drawdowns   = (eq_series - rolling_max) / rolling_max
        max_dd      = drawdowns.min()
        max_dd_pct  = max_dd * 100

        # Peak and trough
        peak_equity  = eq_series.max()
        final_equity = eq_series.iloc[-1]
        total_return = (final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

        # ── SHARPE RATIO (annualised, assuming M5 bars) ────────────────────
        daily_returns = trades_df.groupby(
            pd.to_datetime(trades_df["open_time"]).dt.date
        )["net_pnl"].sum() / INITIAL_CAPITAL

        sharpe = 0.0
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)

        # ── SORTINO RATIO ─────────────────────────────────────────────────
        negative_returns = daily_returns[daily_returns < 0]
        downside_std     = negative_returns.std() if len(negative_returns) > 1 else 0
        sortino = (daily_returns.mean() / downside_std * np.sqrt(252)) if downside_std > 0 else 0

        # ── CALMAR RATIO ──────────────────────────────────────────────────
        annual_return = total_return / max(
            (pd.to_datetime(BACKTEST_END) - pd.to_datetime(BACKTEST_START)).days / 365, 1
        )
        calmar = abs(annual_return / max_dd_pct) if max_dd_pct != 0 else 0

        # ── PER-INSTRUMENT BREAKDOWN ──────────────────────────────────────
        per_instrument = {}
        for sym in trades_df["instrument"].unique():
            sym_df   = trades_df[trades_df["instrument"] == sym]
            sym_wins = sym_df[sym_df["net_pnl"] > 0]
            per_instrument[sym] = {
                "trades":        len(sym_df),
                "wins":          len(sym_wins),
                "losses":        len(sym_df[sym_df["net_pnl"] < 0]),
                "win_rate":      len(sym_wins) / len(sym_df) if len(sym_df) > 0 else 0,
                "net_pnl":       sym_df["net_pnl"].sum(),
                "avg_pnl":       sym_df["net_pnl"].mean(),
                "profit_factor": (
                    sym_wins["net_pnl"].sum() /
                    abs(sym_df[sym_df["net_pnl"] < 0]["net_pnl"].sum())
                    if len(sym_df[sym_df["net_pnl"] < 0]) > 0 else float("inf")
                ),
            }

        # ── MONTHLY RETURNS ───────────────────────────────────────────────
        trades_df["month"] = pd.to_datetime(trades_df["open_time"]).dt.to_period("M")
        monthly_pnl = trades_df.groupby("month")["net_pnl"].sum()

        return {
            # ── Summary ──
            "total_trades":      total_trades,
            "win_count":         win_count,
            "loss_count":        loss_count,
            "breakeven_count":   len(breakevens),
            "win_rate_pct":      win_rate * 100,

            # ── P&L ──
            "net_pnl":           round(net_pnl, 2),
            "gross_profit":      round(gross_profit, 2),
            "gross_loss":        round(gross_loss, 2),
            "profit_factor":     round(profit_factor, 2),
            "avg_win":           round(avg_win, 2),
            "avg_loss":          round(avg_loss, 2),
            "avg_rr":            round(avg_rr, 2),
            "total_commission":  round(trades_df.get("commission", pd.Series([0])).sum(), 2),

            # ── Equity ──
            "initial_capital":   INITIAL_CAPITAL,
            "final_equity":      round(final_equity, 2),
            "peak_equity":       round(peak_equity, 2),
            "total_return_pct":  round(total_return, 2),

            # ── Risk ──
            "max_drawdown_pct":  round(max_dd_pct, 2),
            "max_drawdown_usd":  round(max_dd * peak_equity, 2),

            # ── Ratios ──
            "sharpe_ratio":      round(sharpe, 2),
            "sortino_ratio":     round(sortino, 2),
            "calmar_ratio":      round(calmar, 2),

            # ── Breakdown ──
            "per_instrument":    per_instrument,
            "monthly_pnl":       monthly_pnl.to_dict(),

            # ── Backtest Config ──
            "backtest_start":    BACKTEST_START,
            "backtest_end":      BACKTEST_END,
        }
