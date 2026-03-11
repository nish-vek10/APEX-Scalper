# /scripts/03_plot_results.py
"""
APEX Scalper — Pipeline Step 3: Plot Results
=============================================
Loads backtest_results.pkl and generates all charts:

    1. {INSTRUMENT}_equity_dd.png  — per-asset: equity + drawdown (2-panel)
    2. combined_equity.png          — all assets + portfolio on one chart
    3. portfolio_equity_dd.png      — portfolio: equity + drawdown (2-panel)
    4. all_in_one.png               — full dashboard grid of all panels

MUST run Step 2 first:
    python -m scripts.02_run_backtest

Run from project root:
    python -m scripts.03_plot_results

Output: data/plots/
"""

import os
import sys
import pickle
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")   # Non-interactive backend — works without a display
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import RESULTS_DIR, PLOTS_DIR, INITIAL_CAPITAL
from config.instruments import INSTRUMENT_CONFIG
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────
# CONFIGURABLE VISUAL STYLE
# ─────────────────────────────────────────────
STYLE = {
    "bg":               "#0D1B2A",   # Figure background
    "panel":            "#111D2C",   # Axes background
    "grid":             "#1E2F42",   # Grid lines
    "text":             "#E8E8E8",   # Primary text
    "subtext":          "#7A8FA6",   # Annotation text
    "equity_up":        "#2E86AB",   # Equity line colour
    "fill_up":          "#2E86AB",   # Profit fill
    "fill_dn":          "#E84855",   # Loss fill
    "dd_fill":          "#E84855",   # Drawdown fill
    "zero_line":        "#3A4A5C",   # Zero reference line
    "dpi":              150,
    "fig_single":       (14, 8),
    "fig_combined":     (16, 9),
    "fig_allinone":     (20, 24),
}

# Distinct colour per instrument + portfolio
COLOURS = {
    "XAU_USD":    "#F4D03F",   # Gold
    "SPX500_USD": "#27AE60",   # Green
    "DE30_EUR":   "#3498DB",   # Blue
    "US30_USD":   "#E67E22",   # Orange
    "NAS100_USD": "#9B59B6",   # Purple
    "portfolio":  "#FFFFFF",   # White
}


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _apply_style(fig, axes):
    """Apply unified dark theme to a figure and list of axes."""
    fig.patch.set_facecolor(STYLE["bg"])
    for ax in axes:
        ax.set_facecolor(STYLE["panel"])
        ax.tick_params(colors=STYLE["text"], labelsize=8)
        ax.xaxis.label.set_color(STYLE["text"])
        ax.yaxis.label.set_color(STYLE["text"])
        ax.title.set_color(STYLE["text"])
        for spine in ax.spines.values():
            spine.set_edgecolor(STYLE["grid"])
        ax.grid(True, color=STYLE["grid"], linewidth=0.4, alpha=0.7, linestyle="--")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right",
                 color=STYLE["text"], fontsize=7)
        plt.setp(ax.yaxis.get_majorticklabels(), color=STYLE["text"], fontsize=7)


def _build_equity_series(trade_df: pd.DataFrame) -> pd.Series:
    """
    Build a time-indexed equity series from a trade DataFrame.
    Index = open_time, values = cumulative equity starting from INITIAL_CAPITAL.
    """
    df = trade_df.copy()
    df["open_time"] = pd.to_datetime(df["open_time"])
    df = df.sort_values("open_time").reset_index(drop=True)

    cumulative = INITIAL_CAPITAL + df["net_pnl"].cumsum()
    idx = df["open_time"]
    # Prepend initial capital point
    eq = pd.Series(
        [INITIAL_CAPITAL] + cumulative.tolist(),
        index=pd.to_datetime([idx.iloc[0]] + idx.tolist()),
    )
    return eq


def _drawdown(eq: pd.Series) -> pd.Series:
    """Compute percentage drawdown series from an equity series."""
    peak = eq.cummax()
    return (eq - peak) / peak * 100


def _save(fig, filename: str):
    """Save figure to PLOTS_DIR with consistent settings."""
    path = os.path.join(PLOTS_DIR, filename)
    fig.savefig(path, dpi=STYLE["dpi"], bbox_inches="tight",
                facecolor=STYLE["bg"], edgecolor="none")
    plt.close(fig)
    logger.info(f"  Saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════
# CHART 1 — Per-asset equity + drawdown (2-panel per instrument)
# ═══════════════════════════════════════════════════════════════════════════

def plot_per_asset(trades_df: pd.DataFrame, metrics: dict):
    """
    One 2-panel figure per instrument:
      Top panel (2/3):  equity curve with fill above/below initial capital
      Bottom panel (1/3): drawdown fill
    Saved as: data/plots/{INSTRUMENT}_equity_dd.png
    """
    for symbol, cfg in INSTRUMENT_CONFIG.items():
        inst_df = trades_df[trades_df["instrument"] == symbol]
        if inst_df.empty:
            logger.warning(f"  No trades for {symbol} — skipping per-asset plot.")
            continue

        colour = COLOURS.get(symbol, STYLE["equity_up"])
        name   = cfg["display_name"]
        m      = metrics.get("per_instrument", {}).get(symbol, {})

        eq = _build_equity_series(inst_df)
        dd = _drawdown(eq)

        fig = plt.figure(figsize=STYLE["fig_single"])
        fig.patch.set_facecolor(STYLE["bg"])
        gs  = GridSpec(3, 1, figure=fig, hspace=0.04)
        ax1 = fig.add_subplot(gs[:2, 0])    # Top 2/3 — equity
        ax2 = fig.add_subplot(gs[2, 0], sharex=ax1)   # Bottom 1/3 — drawdown

        # ── Equity panel ──────────────────────────────────────────────────
        ax1.plot(eq.index, eq.values, color=colour, linewidth=1.6,
                 zorder=3, label="Equity")
        ax1.fill_between(eq.index, INITIAL_CAPITAL, eq.values,
                         where=(eq.values >= INITIAL_CAPITAL),
                         alpha=0.18, color=STYLE["fill_up"], zorder=2)
        ax1.fill_between(eq.index, INITIAL_CAPITAL, eq.values,
                         where=(eq.values < INITIAL_CAPITAL),
                         alpha=0.30, color=STYLE["fill_dn"], zorder=2)
        ax1.axhline(INITIAL_CAPITAL, color=STYLE["zero_line"],
                    linewidth=0.9, linestyle="--")

        # Key stats annotation bottom-left
        ann = (
            f"Trades: {m.get('total_trades', 0):,}   "
            f"Win Rate: {m.get('win_rate_pct', 0):.1f}%   "
            f"PF: {m.get('profit_factor', 0):.2f}   "
            f"Net P&L: ${m.get('net_pnl', 0):+,.0f}   "
            f"Sharpe: {m.get('sharpe_ratio', 0):.2f}   "
            f"Max DD: {m.get('max_drawdown_pct', 0):.1f}%"
        )
        ax1.text(0.01, 0.02, ann, transform=ax1.transAxes,
                 fontsize=7.5, color=STYLE["subtext"], va="bottom",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor=STYLE["panel"],
                           edgecolor=STYLE["grid"], alpha=0.7))

        ax1.set_title(f"{name}  —  Equity Curve", fontsize=12,
                      pad=10, color=STYLE["text"], fontweight="bold")
        ax1.set_ylabel("Equity ($)", fontsize=9, color=STYLE["text"])
        ax1.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        plt.setp(ax1.get_xticklabels(), visible=False)

        # ── Drawdown panel ────────────────────────────────────────────────
        ax2.fill_between(dd.index, 0, dd.values,
                         color=STYLE["dd_fill"], alpha=0.65, zorder=2)
        ax2.plot(dd.index, dd.values,
                 color=STYLE["dd_fill"], linewidth=0.8, zorder=3)
        ax2.axhline(0, color=STYLE["zero_line"], linewidth=0.7)
        ax2.set_ylabel("Drawdown (%)", fontsize=9, color=STYLE["text"])
        ax2.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"{x:.1f}%"))

        _apply_style(fig, [ax1, ax2])
        _save(fig, f"{symbol}_equity_dd.png")


# ═══════════════════════════════════════════════════════════════════════════
# CHART 2 — All assets + portfolio on one chart
# ═══════════════════════════════════════════════════════════════════════════

def plot_combined_equity(trades_df: pd.DataFrame, metrics: dict):
    """
    All instrument equity curves + portfolio equity on a single axes.
    Each instrument is a distinct colour; portfolio is white and thicker.
    Saved as: data/plots/combined_equity.png
    """
    fig, ax = plt.subplots(figsize=STYLE["fig_combined"])
    fig.patch.set_facecolor(STYLE["bg"])

    # ── Per-instrument lines ──────────────────────────────────────────────
    for symbol, cfg in INSTRUMENT_CONFIG.items():
        inst_df = trades_df[trades_df["instrument"] == symbol]
        if inst_df.empty:
            continue
        eq     = _build_equity_series(inst_df)
        colour = COLOURS.get(symbol, "#AAAAAA")
        label  = cfg["display_name"]
        m      = metrics.get("per_instrument", {}).get(symbol, {})
        wr     = m.get("win_rate_pct", 0)
        pnl    = m.get("net_pnl", 0)
        ax.plot(eq.index, eq.values, color=colour, linewidth=1.2,
                alpha=0.80, label=f"{label}  ({wr:.0f}% WR  ${pnl:+,.0f})")

    # ── Portfolio line (combined all instruments chronologically) ─────────
    port_eq = _build_equity_series(trades_df)
    port_m  = metrics
    ax.plot(port_eq.index, port_eq.values,
            color=COLOURS["portfolio"], linewidth=2.5, zorder=10,
            label=(f"Portfolio  ({port_m.get('win_rate_pct', 0):.0f}% WR  "
                   f"${port_m.get('net_pnl', 0):+,.0f}  "
                   f"Sharpe {port_m.get('sharpe_ratio', 0):.2f})"))

    ax.axhline(INITIAL_CAPITAL, color=STYLE["zero_line"],
               linewidth=0.8, linestyle="--", alpha=0.5)

    ax.set_title("APEX Scalper — Combined Equity Curves  (2024–2026)",
                 fontsize=14, color=STYLE["text"], pad=14, fontweight="bold")
    ax.set_ylabel("Equity ($)", fontsize=10, color=STYLE["text"])
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    legend = ax.legend(
        facecolor=STYLE["bg"], edgecolor=STYLE["grid"],
        labelcolor=STYLE["text"], fontsize=8.5,
        loc="upper left", framealpha=0.90,
    )

    _apply_style(fig, [ax])
    _save(fig, "combined_equity.png")


# ═══════════════════════════════════════════════════════════════════════════
# CHART 3 — Portfolio equity + drawdown (2-panel)
# ═══════════════════════════════════════════════════════════════════════════

def plot_portfolio_overview(trades_df: pd.DataFrame, metrics: dict):
    """
    Portfolio-level 2-panel: equity (top) + drawdown (bottom).
    Saved as: data/plots/portfolio_equity_dd.png
    """
    eq  = _build_equity_series(trades_df)
    dd  = _drawdown(eq)
    m   = metrics

    fig = plt.figure(figsize=STYLE["fig_single"])
    fig.patch.set_facecolor(STYLE["bg"])
    gs  = GridSpec(3, 1, figure=fig, hspace=0.04)
    ax1 = fig.add_subplot(gs[:2, 0])
    ax2 = fig.add_subplot(gs[2, 0], sharex=ax1)

    # ── Equity panel ──────────────────────────────────────────────────────
    ax1.plot(eq.index, eq.values,
             color=COLOURS["portfolio"], linewidth=2.0, zorder=3)
    ax1.fill_between(eq.index, INITIAL_CAPITAL, eq.values,
                     where=(eq.values >= INITIAL_CAPITAL),
                     alpha=0.12, color=COLOURS["portfolio"], zorder=2)
    ax1.fill_between(eq.index, INITIAL_CAPITAL, eq.values,
                     where=(eq.values < INITIAL_CAPITAL),
                     alpha=0.28, color=STYLE["fill_dn"], zorder=2)
    ax1.axhline(INITIAL_CAPITAL, color=STYLE["zero_line"],
                linewidth=0.8, linestyle="--")

    ann = (
        f"Trades: {m.get('total_trades', 0):,}   "
        f"Win Rate: {m.get('win_rate_pct', 0):.1f}%   "
        f"PF: {m.get('profit_factor', 0):.2f}   "
        f"Net P&L: ${m.get('net_pnl', 0):+,.0f}   "
        f"Return: {m.get('total_return_pct', 0):+.1f}%   "
        f"Max DD: {m.get('max_drawdown_pct', 0):.1f}%   "
        f"Sharpe: {m.get('sharpe_ratio', 0):.2f}   "
        f"Sortino: {m.get('sortino_ratio', 0):.2f}   "
        f"Calmar: {m.get('calmar_ratio', 0):.2f}"
    )
    ax1.text(0.01, 0.02, ann, transform=ax1.transAxes,
             fontsize=7.5, color=STYLE["subtext"], va="bottom",
             bbox=dict(boxstyle="round,pad=0.3", facecolor=STYLE["panel"],
                       edgecolor=STYLE["grid"], alpha=0.7))

    ax1.set_title("APEX Scalper — Portfolio Equity  (2024–2026)",
                  fontsize=12, pad=10, color=STYLE["text"], fontweight="bold")
    ax1.set_ylabel("Equity ($)", fontsize=9, color=STYLE["text"])
    ax1.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    plt.setp(ax1.get_xticklabels(), visible=False)

    # ── Drawdown panel ────────────────────────────────────────────────────
    ax2.fill_between(dd.index, 0, dd.values,
                     color=STYLE["dd_fill"], alpha=0.65, zorder=2)
    ax2.plot(dd.index, dd.values, color=STYLE["dd_fill"],
             linewidth=0.8, zorder=3)
    ax2.axhline(0, color=STYLE["zero_line"], linewidth=0.7)
    ax2.set_ylabel("Drawdown (%)", fontsize=9, color=STYLE["text"])
    ax2.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:.1f}%"))

    _apply_style(fig, [ax1, ax2])
    _save(fig, "portfolio_equity_dd.png")


# ═══════════════════════════════════════════════════════════════════════════
# CHART 4 — All-in-one dashboard grid
# ═══════════════════════════════════════════════════════════════════════════

def plot_all_in_one(trades_df: pd.DataFrame, metrics: dict):
    """
    Grid layout: one equity panel per instrument (2×3 grid) +
    full-width portfolio equity panel at the bottom.
    Saved as: data/plots/all_in_one.png
    """
    instruments = list(INSTRUMENT_CONFIG.keys())
    n_inst = len(instruments)           # 5
    n_cols = 2
    n_rows_inst = (n_inst + 1) // n_cols   # 3 rows for 5 instruments
    n_rows_total = n_rows_inst + 1         # +1 for portfolio row

    fig = plt.figure(figsize=STYLE["fig_allinone"])
    fig.patch.set_facecolor(STYLE["bg"])
    fig.suptitle(
        "APEX Scalper — Full Results Dashboard  (2024–2026)",
        fontsize=16, color=STYLE["text"], y=1.002, fontweight="bold",
    )

    gs = GridSpec(n_rows_total, n_cols, figure=fig,
                  hspace=0.55, wspace=0.28)
    all_axes = []

    # ── Per-instrument panels ─────────────────────────────────────────────
    for idx, symbol in enumerate(instruments):
        row = idx // n_cols
        col = idx % n_cols
        ax  = fig.add_subplot(gs[row, col])
        all_axes.append(ax)

        inst_df = trades_df[trades_df["instrument"] == symbol]
        colour  = COLOURS.get(symbol, STYLE["equity_up"])
        name    = INSTRUMENT_CONFIG[symbol]["display_name"]
        m       = metrics.get("per_instrument", {}).get(symbol, {})

        if inst_df.empty:
            ax.text(0.5, 0.5, "No trades", ha="center", va="center",
                    color=STYLE["subtext"], transform=ax.transAxes, fontsize=10)
            ax.set_title(name, fontsize=10, color=STYLE["text"])
            continue

        eq = _build_equity_series(inst_df)
        ax.plot(eq.index, eq.values, color=colour, linewidth=1.3, zorder=3)
        ax.fill_between(eq.index, INITIAL_CAPITAL, eq.values,
                        where=(eq.values >= INITIAL_CAPITAL),
                        alpha=0.15, color=colour, zorder=2)
        ax.fill_between(eq.index, INITIAL_CAPITAL, eq.values,
                        where=(eq.values < INITIAL_CAPITAL),
                        alpha=0.25, color=STYLE["fill_dn"], zorder=2)
        ax.axhline(INITIAL_CAPITAL, color=STYLE["zero_line"],
                   linewidth=0.7, linestyle="--")

        stats_line = (
            f"Trades {m.get('total_trades',0):,}  "
            f"WR {m.get('win_rate_pct',0):.0f}%  "
            f"PF {m.get('profit_factor',0):.2f}  "
            f"${m.get('net_pnl',0):+,.0f}  "
            f"DD {m.get('max_drawdown_pct',0):.1f}%"
        )
        ax.set_title(f"{name}\n{stats_line}", fontsize=8.5,
                     color=STYLE["text"], pad=5)
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # ── Portfolio panel (full-width bottom row) ───────────────────────────
    ax_port = fig.add_subplot(gs[n_rows_inst, :])
    all_axes.append(ax_port)

    port_eq = _build_equity_series(trades_df)
    m       = metrics

    ax_port.plot(port_eq.index, port_eq.values,
                 color=COLOURS["portfolio"], linewidth=2.0, zorder=3,
                 label="Portfolio")
    ax_port.fill_between(port_eq.index, INITIAL_CAPITAL, port_eq.values,
                         where=(port_eq.values >= INITIAL_CAPITAL),
                         alpha=0.10, color=COLOURS["portfolio"], zorder=2)
    ax_port.fill_between(port_eq.index, INITIAL_CAPITAL, port_eq.values,
                         where=(port_eq.values < INITIAL_CAPITAL),
                         alpha=0.25, color=STYLE["fill_dn"], zorder=2)
    ax_port.axhline(INITIAL_CAPITAL, color=STYLE["zero_line"],
                    linewidth=0.8, linestyle="--")

    port_stats = (
        f"Portfolio Combined   "
        f"Trades {m.get('total_trades',0):,}  "
        f"WR {m.get('win_rate_pct',0):.1f}%  "
        f"PF {m.get('profit_factor',0):.2f}  "
        f"Net P&L ${m.get('net_pnl',0):+,.0f}  "
        f"Return {m.get('total_return_pct',0):+.1f}%  "
        f"Max DD {m.get('max_drawdown_pct',0):.1f}%  "
        f"Sharpe {m.get('sharpe_ratio',0):.2f}"
    )
    ax_port.set_title(port_stats, fontsize=9, color=STYLE["text"], pad=7)
    ax_port.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    _apply_style(fig, all_axes)
    _save(fig, "all_in_one.png")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def plot_all():
    os.makedirs(PLOTS_DIR, exist_ok=True)

    pkl_path = os.path.join(RESULTS_DIR, "backtest_results.pkl")
    if not os.path.exists(pkl_path):
        logger.error(
            f"Results file not found: {pkl_path}\n"
            f"  → Run Step 2 first:  python -m scripts.02_run_backtest"
        )
        return

    with open(pkl_path, "rb") as f:
        results = pickle.load(f)

    trades_df = pd.DataFrame(results.get("trades", []))
    metrics   = results.get("metrics", {})

    if trades_df.empty:
        logger.error("No trades found in results. Cannot generate plots.")
        return

    logger.info("=" * 60)
    logger.info("  APEX SCALPER — STEP 3: PLOTTING")
    logger.info("=" * 60)

    logger.info("  [1/4] Per-asset equity + drawdown charts ...")
    plot_per_asset(trades_df, metrics)

    logger.info("  [2/4] Combined equity chart ...")
    plot_combined_equity(trades_df, metrics)

    logger.info("  [3/4] Portfolio equity + drawdown chart ...")
    plot_portfolio_overview(trades_df, metrics)

    logger.info("  [4/4] All-in-one dashboard ...")
    plot_all_in_one(trades_df, metrics)

    logger.info("=" * 60)
    logger.info(f"  All plots saved to: {PLOTS_DIR}/")
    logger.info("  Next step → python -m scripts.04_generate_report")
    logger.info("=" * 60)


if __name__ == "__main__":
    plot_all()
