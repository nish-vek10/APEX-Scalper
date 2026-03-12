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

    # # ── WTI Crude Oil ─────────────────────────────────────────────────────
    # "WTICO_USD": {
    #     "mt5_symbol":       "USOIL",
    #     "display_name":     "WTI Crude Oil (WTICO)",
    #     "pip_size":         0.01,            # 1 pip = $0.01
    #     "pip_value_per_lot":10.0,            # USD per pip per standard lot (1,000 barrels)
    #     "min_lot":          1.0,
    #     "lot_step":         1.0,
    #     "max_lot":          100.0,
    #     "typical_spread":   0.03,            # Typical spread in price units
    #     "digits":           2,
    #     "sessions": {
    #         "london": ("07:00", "12:00"),    # Active through London + NY overlap
    #         "ny":     ("12:00", "20:00"),
    #         "active": ("07:00", "20:00"),    # UTC — most liquid window
    #     },
    #     "currency":         "USD",
    #     "asset_class":      "commodity",
    #     "atr_floor_pips":   5.0,
    #     "atr_ceiling_pips": 150.0,
    #     "magic_number":     10006,
    # },
    #
    # # ── Euro / US Dollar ──────────────────────────────────────────────────
    # "EUR_USD": {
    #     "mt5_symbol":       "EURUSD",
    #     "display_name":     "Euro / US Dollar (EURUSD)",
    #     "pip_size":         0.0001,          # 1 pip = 0.0001
    #     "pip_value_per_lot":10.0,            # USD per pip per standard lot (100k units)
    #     "min_lot":          0.01,
    #     "lot_step":         0.01,
    #     "max_lot":          100.0,
    #     "typical_spread":   0.8,             # Typical spread in pips
    #     "digits":           5,
    #     "sessions": {
    #         "london": ("07:00", "12:00"),    # Peak liquidity window
    #         "ny":     ("12:00", "17:00"),
    #         "active": ("07:00", "17:00"),    # London open → NY close UTC
    #     },
    #     "currency":         "USD",
    #     "asset_class":      "fx",
    #     "atr_floor_pips":   3.0,
    #     "atr_ceiling_pips": 50.0,
    #     "magic_number":     10007,
    # },
    #
    # # ── US Dollar / Japanese Yen ──────────────────────────────────────────
    # "USD_JPY": {
    #     "mt5_symbol":       "USDJPY",
    #     "display_name":     "US Dollar / Japanese Yen (USDJPY)",
    #     "pip_size":         0.01,            # 1 pip = 0.01 (JPY pairs use 2dp)
    #     "pip_value_per_lot":9.0,             # USD per pip per lot (approx, varies with rate)
    #     "min_lot":          0.01,
    #     "lot_step":         0.01,
    #     "max_lot":          100.0,
    #     "typical_spread":   0.8,             # Typical spread in pips
    #     "digits":           3,
    #     "sessions": {
    #         "tokyo":  ("00:00", "09:00"),    # Tokyo session UTC
    #         "london": ("07:00", "17:00"),    # London session UTC
    #         "active": ("00:00", "17:00"),    # Tokyo open → London close UTC
    #     },
    #     "currency":         "USD",
    #     "asset_class":      "fx",
    #     "atr_floor_pips":   3.0,
    #     "atr_ceiling_pips": 80.0,
    #     "magic_number":     10008,
    # },
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
