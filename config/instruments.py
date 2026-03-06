# /config/instruments.py
"""
APEX Scalper — Instrument-Specific Configuration
==================================================
Per-asset parameters including pip values, typical spreads,
trading sessions, and contract specs.
All times are in UTC.
"""

INSTRUMENT_CONFIG = {

    # ── Gold ──────────────────────────────────────────────────────────────
    "XAU_USD": {
        "mt5_symbol":       "XAUUSD",
        "display_name":     "Gold (XAUUSD)",
        "pip_size":         0.01,            # 1 pip = $0.01 on XAUUSD
        "pip_value_per_lot":10.0,            # USD value per pip per standard lot
        "min_lot":          0.01,            # Minimum lot size
        "lot_step":         0.01,            # Lot size increment
        "max_lot":          50.0,            # Maximum lot size
        "typical_spread":   0.30,            # Typical spread in pips
        "digits":           2,               # Price decimal places
        "sessions": {
            "london": ("07:00", "12:00"),    # UTC open/close
            "ny":     ("12:00", "17:00"),    # UTC open/close
            "active": ("07:00", "17:00"),    # Full active window
        },
        "currency":         "USD",
        "asset_class":      "commodity",
        "atr_floor_pips":   3.0,             # Minimum ATR to trade (pips)
        "atr_ceiling_pips": 50.0,            # Maximum ATR to trade (news spike filter)
        "magic_number":     10001,           # MT5 magic number for trade identification
    },

    # ── S&P 500 ───────────────────────────────────────────────────────────
    "SPX500_USD": {
        "mt5_symbol":       "SP500",
        "display_name":     "S&P 500 (SPX500)",
        "pip_size":         0.10,            # 1 pip = 0.10 index points
        "pip_value_per_lot":1.0,             # USD per pip per lot
        "min_lot":          1.0,
        "lot_step":         1.0,
        "max_lot":          100.0,
        "typical_spread":   0.40,            # Points
        "digits":           1,
        "sessions": {
            "premarket": ("12:00", "13:30"),
            "ny":        ("13:30", "20:00"),
            "active":    ("13:30", "20:00"), # NYSE hours UTC
        },
        "currency":         "USD",
        "asset_class":      "index",
        "atr_floor_pips":   5.0,
        "atr_ceiling_pips": 100.0,
        "magic_number":     10002,
    },

    # ── DAX ───────────────────────────────────────────────────────────────
    "DE30_EUR": {
        "mt5_symbol":       "GER30",
        "display_name":     "DAX 40 (DE30)",
        "pip_size":         0.10,
        "pip_value_per_lot":1.0,             # EUR per pip (converted at runtime)
        "min_lot":          1.0,
        "lot_step":         1.0,
        "max_lot":          100.0,
        "typical_spread":   0.80,
        "digits":           1,
        "sessions": {
            "frankfurt": ("07:00", "09:00"),
            "london":    ("08:00", "16:30"),
            "active":    ("07:00", "15:30"), # Xetra hours UTC
        },
        "currency":         "EUR",
        "asset_class":      "index",
        "atr_floor_pips":   10.0,
        "atr_ceiling_pips": 200.0,
        "magic_number":     10003,
    },

    # ── Dow Jones ─────────────────────────────────────────────────────────
    "US30_USD": {
        "mt5_symbol":       "US30",
        "display_name":     "Dow Jones (US30)",
        "pip_size":         0.10,
        "pip_value_per_lot":1.0,
        "min_lot":          1.0,
        "lot_step":         1.0,
        "max_lot":          100.0,
        "typical_spread":   1.50,
        "digits":           1,
        "sessions": {
            "ny":     ("13:30", "20:00"),
            "active": ("13:30", "20:00"),
        },
        "currency":         "USD",
        "asset_class":      "index",
        "atr_floor_pips":   10.0,
        "atr_ceiling_pips": 300.0,
        "magic_number":     10004,
    },

    # ── Nasdaq 100 ────────────────────────────────────────────────────────
    "NAS100_USD": {
        "mt5_symbol":       "NAS100",
        "display_name":     "Nasdaq 100 (NAS100)",
        "pip_size":         0.10,
        "pip_value_per_lot":1.0,
        "min_lot":          1.0,
        "lot_step":         1.0,
        "max_lot":          100.0,
        "typical_spread":   0.80,
        "digits":           1,
        "sessions": {
            "ny":     ("13:30", "20:00"),
            "active": ("13:30", "20:00"),
        },
        "currency":         "USD",
        "asset_class":      "index",
        "atr_floor_pips":   5.0,
        "atr_ceiling_pips": 200.0,
        "magic_number":     10005,
    },
}


def get_instrument(oanda_symbol: str) -> dict:
    """Return config dict for a given Oanda instrument symbol."""
    config = INSTRUMENT_CONFIG.get(oanda_symbol)
    if config is None:
        raise ValueError(f"Instrument '{oanda_symbol}' not found in INSTRUMENT_CONFIG.")
    return config


def get_all_oanda_symbols() -> list:
    """Return list of all Oanda instrument symbols configured."""
    return list(INSTRUMENT_CONFIG.keys())


def get_mt5_symbol(oanda_symbol: str) -> str:
    """Translate an Oanda symbol to its corresponding MT5 symbol name."""
    return INSTRUMENT_CONFIG[oanda_symbol]["mt5_symbol"]


def get_magic_number(oanda_symbol: str) -> int:
    """Return the MT5 magic number for a given instrument."""
    return INSTRUMENT_CONFIG[oanda_symbol]["magic_number"]
