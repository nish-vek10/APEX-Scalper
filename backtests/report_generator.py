# /backtests/report_generator.py
"""
APEX Scalper — Excel Report Generator
========================================
Generates a professional, investor-grade Excel backtest report.

Sheets produced:
    1. Summary Dashboard   — Key metrics, strategy overview, performance ratings
    2. Per-Instrument      — Breakdown by asset with colour-coded performance
    3. Monthly Returns     — Heatmap of monthly P&L
    4. Trade Log           — Full trade-by-trade detail
    5. Equity Curve        — Chart of account growth over backtest period

Requires: openpyxl, XlsxWriter
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime

import xlsxwriter
from xlsxwriter.utility import xl_rowcol_to_cell

from config.settings import BACKTEST_START, BACKTEST_END, INITIAL_CAPITAL
from config.instruments import INSTRUMENT_CONFIG
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────
# COLOUR PALETTE — consistent brand throughout the report
# ─────────────────────────────────────────────────────────────────────────
COLORS = {
    "navy":       "#0D1B2A",    # Header backgrounds
    "gold":       "#C9A84C",    # Accent / highlight
    "dark_grey":  "#2D3142",    # Sub-header backgrounds
    "mid_grey":   "#4F5D75",    # Section dividers
    "light_grey": "#F4F4F4",    # Alternate row fill
    "white":      "#FFFFFF",
    "green":      "#27AE60",    # Positive P&L
    "red":        "#E74C3C",    # Negative P&L
    "amber":      "#F39C12",    # Warning / neutral
    "light_green":"#D5F5E3",    # Positive cell fill
    "light_red":  "#FADBD8",    # Negative cell fill
    "light_amber":"#FDEBD0",    # Neutral cell fill
    "chart_blue": "#2E86AB",    # Equity curve line
    "chart_red":  "#E84855",    # Drawdown area
}

OUTPUT_DIR = "backtests/reports"


class ReportGenerator:
    """
    Generates a multi-sheet Excel report from backtest results.
    """

    def generate(
        self,
        metrics:      dict,
        trades:       list,
        equity_curve: pd.Series,
        filename:     str = None,
    ) -> str:
        """
        Generate the full Excel report and save to the reports directory.

        Args:
            metrics:      Performance metrics dict from BacktestEngine._compute_metrics()
            trades:       List of trade dicts from BacktestEngine
            equity_curve: pd.Series of equity values (index = datetime)
            filename:     Optional custom filename (auto-generated if None)

        Returns:
            str: Full path to saved Excel file
        """
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        if filename is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"APEX_Scalper_Backtest_{BACKTEST_START}_{BACKTEST_END}_{ts}.xlsx"

        filepath = os.path.join(OUTPUT_DIR, filename)

        # Create workbook with XlsxWriter
        wb = xlsxwriter.Workbook(filepath, {"nan_inf_to_errors": True})

        # Precompute all formats
        fmt = self._build_formats(wb)

        # Build each sheet
        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()

        self._sheet_summary(wb, fmt, metrics)
        self._sheet_per_instrument(wb, fmt, metrics)
        self._sheet_monthly_returns(wb, fmt, metrics, trades_df)
        self._sheet_trade_log(wb, fmt, trades_df)
        self._sheet_equity_curve(wb, fmt, equity_curve, metrics)

        wb.close()

        logger.info(f"Report saved: {filepath}")
        return filepath

    # ─────────────────────────────────────────────────────────────────────
    # SHEET 1: SUMMARY DASHBOARD
    # ─────────────────────────────────────────────────────────────────────

    def _sheet_summary(self, wb, fmt, metrics):
        ws = wb.add_worksheet("Summary")
        ws.set_tab_color(COLORS["gold"])

        # Column widths
        ws.set_column("A:A", 32)
        ws.set_column("B:B", 22)
        ws.set_column("C:C", 32)
        ws.set_column("D:D", 22)
        ws.set_column("E:E", 2)

        # ── Title Banner ─────────────────────────────────────────────────
        ws.merge_range("A1:D1", "APEX SCALPER — BACKTEST REPORT", fmt["title"])
        ws.merge_range("A2:D2",
            f"Strategy: APEX Scalper  |  Period: {metrics.get('backtest_start')} → {metrics.get('backtest_end')}  |  "
            f"Generated: {datetime.now().strftime('%d %b %Y %H:%M')}",
            fmt["subtitle"]
        )
        ws.set_row(0, 36)
        ws.set_row(1, 20)

        # ── Section: Account Performance ──────────────────────────────────
        r = 3
        ws.merge_range(f"A{r}:D{r}", "ACCOUNT PERFORMANCE", fmt["section_header"])
        r += 1

        acc_data = [
            ("Initial Capital",    f"${metrics.get('initial_capital', 0):,.2f}",
             "Final Equity",       f"${metrics.get('final_equity', 0):,.2f}"),
            ("Net P&L",            f"${metrics.get('net_pnl', 0):+,.2f}",
             "Total Return",       f"{metrics.get('total_return_pct', 0):+.2f}%"),
            ("Peak Equity",        f"${metrics.get('peak_equity', 0):,.2f}",
             "Total Commission",   f"${metrics.get('total_commission', 0):,.2f}"),
        ]

        for label_a, val_a, label_b, val_b in acc_data:
            ws.write(f"A{r}", label_a, fmt["label"])
            ws.write(f"B{r}", val_a,   fmt["value_highlight"] if "P&L" in label_a or "Return" in label_a else fmt["value"])
            ws.write(f"C{r}", label_b, fmt["label"])
            ws.write(f"D{r}", val_b,   fmt["value"])
            r += 1

        r += 1
        # ── Section: Trade Statistics ─────────────────────────────────────
        ws.merge_range(f"A{r}:D{r}", "TRADE STATISTICS", fmt["section_header"])
        r += 1

        trade_data = [
            ("Total Trades",       str(metrics.get("total_trades", 0)),
             "Win Rate",           f"{metrics.get('win_rate_pct', 0):.1f}%"),
            ("Winning Trades",     str(metrics.get("win_count", 0)),
             "Losing Trades",      str(metrics.get("loss_count", 0))),
            ("Average Win",        f"${metrics.get('avg_win', 0):+.2f}",
             "Average Loss",       f"${metrics.get('avg_loss', 0):+.2f}"),
            ("Profit Factor",      f"{metrics.get('profit_factor', 0):.2f}",
             "Average R:R",        f"{metrics.get('avg_rr', 0):.2f}"),
            ("Gross Profit",       f"${metrics.get('gross_profit', 0):,.2f}",
             "Gross Loss",         f"${metrics.get('gross_loss', 0):,.2f}"),
        ]

        for label_a, val_a, label_b, val_b in trade_data:
            ws.write(f"A{r}", label_a, fmt["label"])
            ws.write(f"B{r}", val_a,   fmt["value"])
            ws.write(f"C{r}", label_b, fmt["label"])
            ws.write(f"D{r}", val_b,   fmt["value"])
            r += 1

        r += 1
        # ── Section: Risk Metrics ──────────────────────────────────────────
        ws.merge_range(f"A{r}:D{r}", "RISK METRICS", fmt["section_header"])
        r += 1

        risk_data = [
            ("Max Drawdown (%)",    f"{metrics.get('max_drawdown_pct', 0):.2f}%",
             "Max Drawdown (USD)",  f"${abs(metrics.get('max_drawdown_usd', 0)):,.2f}"),
            ("Sharpe Ratio",        f"{metrics.get('sharpe_ratio', 0):.2f}",
             "Sortino Ratio",       f"{metrics.get('sortino_ratio', 0):.2f}"),
            ("Calmar Ratio",        f"{metrics.get('calmar_ratio', 0):.2f}",
             "Risk per Trade",      "0.50% (Base)"),
        ]

        for label_a, val_a, label_b, val_b in risk_data:
            ws.write(f"A{r}", label_a, fmt["label"])
            ws.write(f"B{r}", val_a,   fmt["value"])
            ws.write(f"C{r}", label_b, fmt["label"])
            ws.write(f"D{r}", val_b,   fmt["value"])
            r += 1

        r += 1
        # ── Section: Strategy Configuration ───────────────────────────────
        ws.merge_range(f"A{r}:D{r}", "STRATEGY CONFIGURATION", fmt["section_header"])
        r += 1

        config_data = [
            ("Entry Timeframe",    "M5",
             "Bias Timeframe",     "M15 + H1"),
            ("Min Signal Score",   "5/10",
             "Max Signal Score",   "10/10"),
            ("SL Multiplier",      "1.5x ATR",
             "TP Structure",       "1:1 / 1:2 / 1:3 (Tiered)"),
            ("Instruments",        "XAUUSD, SPX500, DE30, US30, NAS100",
             "Slippage",           "0.5 pips"),
        ]

        for label_a, val_a, label_b, val_b in config_data:
            ws.write(f"A{r}", label_a, fmt["label"])
            ws.write(f"B{r}", val_a,   fmt["value"])
            ws.write(f"C{r}", label_b, fmt["label"])
            ws.write(f"D{r}", val_b,   fmt["value"])
            r += 1

        # ── Performance Rating ─────────────────────────────────────────────
        r += 1
        ws.merge_range(f"A{r}:D{r}", "PERFORMANCE RATING", fmt["section_header"])
        r += 1

        def rating(label, value, good, ok, fmt_good, fmt_amber, fmt_bad):
            if value >= good:
                style = fmt_good
            elif value >= ok:
                style = fmt_amber
            else:
                style = fmt_bad
            ws.write(f"A{r}", label, fmt["label"])
            ws.write(f"B{r}", value, style)

        win_rate = metrics.get("win_rate_pct", 0)
        pf       = metrics.get("profit_factor", 0)
        sharpe   = metrics.get("sharpe_ratio",  0)
        dd       = abs(metrics.get("max_drawdown_pct", 0))

        ratings = [
            ("Win Rate",       f"{win_rate:.1f}%", 60, 50, fmt["rating_green"], fmt["rating_amber"], fmt["rating_red"]),
            ("Profit Factor",  f"{pf:.2f}",        1.5, 1.2, fmt["rating_green"], fmt["rating_amber"], fmt["rating_red"]),
            ("Sharpe Ratio",   f"{sharpe:.2f}",    1.5, 0.8, fmt["rating_green"], fmt["rating_amber"], fmt["rating_red"]),
            ("Max Drawdown",   f"{dd:.2f}%",       None, None, None, None, None),
        ]

        for label, val, good, ok, fg, fa, fb in ratings:
            ws.write(f"A{r}", label, fmt["label"])
            if good is None:
                dd_fmt = fmt["rating_green"] if dd < 5 else fmt["rating_amber"] if dd < 15 else fmt["rating_red"]
                ws.write(f"B{r}", val, dd_fmt)
            else:
                float_val = float(val.replace("%","").replace("x",""))
                style = fg if float_val >= good else fa if float_val >= ok else fb
                ws.write(f"B{r}", val, style)
            r += 1

    # ─────────────────────────────────────────────────────────────────────
    # SHEET 2: PER-INSTRUMENT BREAKDOWN
    # ─────────────────────────────────────────────────────────────────────

    def _sheet_per_instrument(self, wb, fmt, metrics):
        ws = wb.add_worksheet("Per-Instrument")
        ws.set_tab_color(COLORS["navy"])

        ws.merge_range("A1:J1", "PERFORMANCE BY INSTRUMENT", fmt["title"])
        ws.set_row(0, 32)

        headers = ["Instrument", "Trades", "Wins", "Losses",
                   "Win Rate", "Net P&L ($)", "Avg P&L ($)",
                   "Profit Factor", "Best Trade", "Worst Trade"]

        col_widths = [20, 10, 10, 10, 12, 15, 15, 15, 15, 15]
        for i, (h, w) in enumerate(zip(headers, col_widths)):
            ws.set_column(i, i, w)
            ws.write(1, i, h, fmt["col_header"])

        per_inst = metrics.get("per_instrument", {})
        for row_i, (sym, data) in enumerate(per_inst.items()):
            r = row_i + 2
            display_name = INSTRUMENT_CONFIG.get(sym, {}).get("display_name", sym)
            alt_fmt      = fmt["alt_row"] if row_i % 2 == 0 else fmt["normal_row"]

            win_rate_val = data["win_rate"] * 100
            net_pnl_val  = data["net_pnl"]
            pf_val       = data["profit_factor"]

            # Colour-code win rate
            wr_fmt = fmt["cell_green"] if win_rate_val >= 55 else fmt["cell_amber"] if win_rate_val >= 45 else fmt["cell_red"]
            # Colour-code P&L
            pnl_fmt= fmt["cell_green"] if net_pnl_val > 0 else fmt["cell_red"]

            ws.write(r, 0, display_name,                   alt_fmt)
            ws.write(r, 1, data["trades"],                 alt_fmt)
            ws.write(r, 2, data["wins"],                   alt_fmt)
            ws.write(r, 3, data["losses"],                 alt_fmt)
            ws.write(r, 4, f"{win_rate_val:.1f}%",        wr_fmt)
            ws.write(r, 5, f"${net_pnl_val:+,.2f}",       pnl_fmt)
            ws.write(r, 6, f"${data['avg_pnl']:+.2f}",    alt_fmt)
            ws.write(r, 7, f"{pf_val:.2f}" if pf_val != float('inf') else "∞", alt_fmt)
            ws.write(r, 8, "N/A",                          alt_fmt)
            ws.write(r, 9, "N/A",                          alt_fmt)

    # ─────────────────────────────────────────────────────────────────────
    # SHEET 3: MONTHLY RETURNS HEATMAP
    # ─────────────────────────────────────────────────────────────────────

    def _sheet_monthly_returns(self, wb, fmt, metrics, trades_df):
        ws = wb.add_worksheet("Monthly Returns")
        ws.set_tab_color(COLORS["mid_grey"])
        ws.merge_range("A1:N1", "MONTHLY RETURNS HEATMAP (USD)", fmt["title"])
        ws.set_row(0, 32)

        months_map = {
            1:"Jan", 2:"Feb", 3:"Mar", 4:"Apr", 5:"May", 6:"Jun",
            7:"Jul", 8:"Aug", 9:"Sep", 10:"Oct", 11:"Nov", 12:"Dec"
        }

        ws.write(1, 0, "Year", fmt["col_header"])
        for m_num, m_name in months_map.items():
            ws.write(1, m_num, m_name, fmt["col_header"])
        ws.write(1, 13, "Annual Total", fmt["col_header"])

        ws.set_column(0, 0, 10)
        for c in range(1, 14):
            ws.set_column(c, c, 13)

        if trades_df.empty:
            ws.write(2, 0, "No trades data", fmt["normal_row"])
            return

        trades_df["open_time"] = pd.to_datetime(trades_df["open_time"])
        trades_df["year"]  = trades_df["open_time"].dt.year
        trades_df["month"] = trades_df["open_time"].dt.month

        pivot = trades_df.groupby(["year", "month"])["net_pnl"].sum().unstack(fill_value=0)

        for row_i, (year, row_data) in enumerate(pivot.iterrows()):
            r = row_i + 2
            ws.write(r, 0, str(year), fmt["label"])
            annual_total = 0
            for m_num in range(1, 13):
                val = row_data.get(m_num, 0)
                annual_total += val
                if val > 0:
                    cell_fmt = fmt["cell_green"]
                elif val < 0:
                    cell_fmt = fmt["cell_red"]
                else:
                    cell_fmt = fmt["normal_row"]
                ws.write(r, m_num, f"${val:+,.0f}" if val != 0 else "-", cell_fmt)

            annual_fmt = fmt["cell_green"] if annual_total > 0 else fmt["cell_red"]
            ws.write(r, 13, f"${annual_total:+,.0f}", annual_fmt)

    # ─────────────────────────────────────────────────────────────────────
    # SHEET 4: TRADE LOG
    # ─────────────────────────────────────────────────────────────────────

    def _sheet_trade_log(self, wb, fmt, trades_df):
        ws = wb.add_worksheet("Trade Log")
        ws.set_tab_color(COLORS["dark_grey"])
        ws.merge_range("A1:M1", "COMPLETE TRADE LOG", fmt["title"])
        ws.set_row(0, 32)

        headers = ["#", "Instrument", "Direction", "Open Time", "Close Time",
                   "Entry Price", "Exit Price", "Lots", "SL (pips)",
                   "Pips P&L", "Gross P&L ($)", "Commission ($)", "Net P&L ($)"]
        widths   = [6, 18, 12, 20, 20, 14, 14, 10, 10, 12, 14, 14, 14]

        for i, (h, w) in enumerate(zip(headers, widths)):
            ws.set_column(i, i, w)
            ws.write(1, i, h, fmt["col_header"])

        if trades_df.empty:
            ws.write(2, 0, "No trades executed.", fmt["normal_row"])
            return

        for row_i, trade in trades_df.iterrows():
            r = row_i + 2
            alt_fmt  = fmt["alt_row"] if row_i % 2 == 0 else fmt["normal_row"]
            net_pnl  = trade.get("net_pnl", trade.get("usd_pnl", 0))
            pnl_fmt  = fmt["cell_green"] if net_pnl > 0 else fmt["cell_red"] if net_pnl < 0 else alt_fmt
            dir_fmt  = fmt["dir_long"] if str(trade.get("direction","")).lower() == "long" else fmt["dir_short"]

            ws.write(r, 0, row_i + 1,                                            alt_fmt)
            ws.write(r, 1, str(trade.get("instrument", "")),                     alt_fmt)
            ws.write(r, 2, str(trade.get("direction", "")).upper(),              dir_fmt)
            ws.write(r, 3, str(trade.get("open_time",  ""))[:19],               alt_fmt)
            ws.write(r, 4, str(trade.get("close_time", ""))[:19],               alt_fmt)
            ws.write(r, 5, f"{trade.get('entry_price', 0):.5f}",                alt_fmt)
            ws.write(r, 6, f"{trade.get('exit_price',  0):.5f}",                alt_fmt)
            ws.write(r, 7, f"{trade.get('lots', 0):.2f}",                       alt_fmt)
            ws.write(r, 8, f"{trade.get('sl_pips', 0):.1f}" if 'sl_pips' in trade else "-", alt_fmt)
            ws.write(r, 9, f"{trade.get('pips_pnl', 0):+.1f}",                 pnl_fmt)
            ws.write(r,10, f"${trade.get('usd_pnl', 0):+.2f}",                 alt_fmt)
            ws.write(r,11, f"${trade.get('commission', 0):.2f}",                alt_fmt)
            ws.write(r,12, f"${net_pnl:+.2f}",                                 pnl_fmt)

        # Totals row
        total_row = len(trades_df) + 2
        ws.merge_range(total_row, 0, total_row, 11, "TOTALS", fmt["col_header"])
        total_net = trades_df.apply(
            lambda t: t.get("net_pnl", t.get("usd_pnl", 0)), axis=1
        ).sum()
        pnl_fmt = fmt["cell_green"] if total_net > 0 else fmt["cell_red"]
        ws.write(total_row, 12, f"${total_net:+.2f}", pnl_fmt)

    # ─────────────────────────────────────────────────────────────────────
    # SHEET 5: EQUITY CURVE
    # ─────────────────────────────────────────────────────────────────────

    def _sheet_equity_curve(self, wb, fmt, equity_curve: pd.Series, metrics):
        ws = wb.add_worksheet("Equity Curve")
        ws.set_tab_color(COLORS["chart_blue"])
        ws.merge_range("A1:B1", "EQUITY CURVE DATA", fmt["title"])
        ws.set_row(0, 32)

        ws.write(1, 0, "Timestamp",     fmt["col_header"])
        ws.write(1, 1, "Equity ($)",    fmt["col_header"])
        ws.write(1, 2, "Drawdown (%)",  fmt["col_header"])
        ws.set_column(0, 0, 24)
        ws.set_column(1, 1, 16)
        ws.set_column(2, 2, 16)

        if equity_curve is None or len(equity_curve) == 0:
            ws.write(2, 0, "No equity data.", fmt["normal_row"])
            return

        eq_values  = equity_curve.values
        roll_max   = pd.Series(eq_values).cummax().values
        dd_values  = (eq_values - roll_max) / roll_max * 100

        for i, (ts, eq) in enumerate(equity_curve.items()):
            r = i + 2
            ws.write(r, 0, str(ts)[:19],          fmt["normal_row"])
            ws.write(r, 1, round(float(eq), 2),   fmt["normal_row"])
            ws.write(r, 2, round(float(dd_values[i]), 2), fmt["normal_row"])

        # ── Equity Curve Chart ─────────────────────────────────────────────
        n_rows = len(equity_curve)
        chart  = wb.add_chart({"type": "line"})

        chart.add_series({
            "name":       "Equity ($)",
            "categories": ["Equity Curve", 2, 0, n_rows + 1, 0],
            "values":     ["Equity Curve", 2, 1, n_rows + 1, 1],
            "line":       {"color": COLORS["chart_blue"], "width": 2.0},
        })

        chart.set_title({"name": "APEX Scalper — Equity Curve"})
        chart.set_x_axis({"name": "Time", "date_axis": False})
        chart.set_y_axis({"name": "Account Equity ($)"})
        chart.set_legend({"position": "bottom"})
        chart.set_size({"width": 900, "height": 400})
        chart.set_chartarea({"border": {"color": COLORS["navy"]},
                              "fill":   {"color": COLORS["white"]}})

        ws.insert_chart("E3", chart)

    # ─────────────────────────────────────────────────────────────────────
    # FORMAT BUILDER
    # ─────────────────────────────────────────────────────────────────────

    def _build_formats(self, wb) -> dict:
        """Build and return all reusable XlsxWriter format objects."""

        def f(**kwargs):
            return wb.add_format(kwargs)

        base = {"font_name": "Calibri", "font_size": 10, "border": 1,
                "border_color": "#CCCCCC", "valign": "vcenter"}

        def merge(a, b):
            return {**a, **b}

        return {
            # ── Title / Header ─────────────────────────────────────────────
            "title": f(**merge(base, {
                "bold": True, "font_size": 16,
                "bg_color": COLORS["navy"], "font_color": COLORS["gold"],
                "align": "center", "valign": "vcenter", "border": 0
            })),
            "subtitle": f(**merge(base, {
                "italic": True, "font_size": 9,
                "bg_color": COLORS["dark_grey"], "font_color": "#AAAAAA",
                "align": "center", "border": 0
            })),
            "section_header": f(**merge(base, {
                "bold": True, "font_size": 11,
                "bg_color": COLORS["dark_grey"], "font_color": COLORS["gold"],
                "align": "left", "border": 0, "top": 2, "bottom": 2,
                "top_color": COLORS["gold"], "bottom_color": COLORS["gold"]
            })),
            "col_header": f(**merge(base, {
                "bold": True, "font_size": 10,
                "bg_color": COLORS["navy"], "font_color": COLORS["white"],
                "align": "center", "border": 1, "border_color": COLORS["mid_grey"]
            })),

            # ── Data cells ─────────────────────────────────────────────────
            "label": f(**merge(base, {
                "bold": True, "font_color": "#333333",
                "bg_color": "#E8EBF0", "align": "left"
            })),
            "value": f(**merge(base, {
                "align": "right", "font_color": "#1A1A2E",
                "bg_color": COLORS["white"]
            })),
            "value_highlight": f(**merge(base, {
                "bold": True, "align": "right",
                "font_color": COLORS["navy"], "bg_color": "#FFFDE7"
            })),
            "normal_row": f(**merge(base, {
                "bg_color": COLORS["white"], "align": "center"
            })),
            "alt_row": f(**merge(base, {
                "bg_color": COLORS["light_grey"], "align": "center"
            })),

            # ── Colour-coded cells ─────────────────────────────────────────
            "cell_green": f(**merge(base, {
                "bold": True, "font_color": "#155724",
                "bg_color": COLORS["light_green"], "align": "center"
            })),
            "cell_red": f(**merge(base, {
                "bold": True, "font_color": "#721C24",
                "bg_color": COLORS["light_red"], "align": "center"
            })),
            "cell_amber": f(**merge(base, {
                "bold": True, "font_color": "#856404",
                "bg_color": COLORS["light_amber"], "align": "center"
            })),

            # ── Rating cells ───────────────────────────────────────────────
            "rating_green": f(**merge(base, {
                "bold": True, "font_size": 11,
                "font_color": COLORS["white"], "bg_color": COLORS["green"],
                "align": "center", "border": 0
            })),
            "rating_amber": f(**merge(base, {
                "bold": True, "font_size": 11,
                "font_color": COLORS["white"], "bg_color": COLORS["amber"],
                "align": "center", "border": 0
            })),
            "rating_red": f(**merge(base, {
                "bold": True, "font_size": 11,
                "font_color": COLORS["white"], "bg_color": COLORS["red"],
                "align": "center", "border": 0
            })),

            # ── Direction indicators ───────────────────────────────────────
            "dir_long": f(**merge(base, {
                "bold": True, "font_color": COLORS["green"],
                "bg_color": COLORS["light_green"], "align": "center"
            })),
            "dir_short": f(**merge(base, {
                "bold": True, "font_color": COLORS["red"],
                "bg_color": COLORS["light_red"], "align": "center"
            })),
        }
