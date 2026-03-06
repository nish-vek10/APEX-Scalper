# /src/data/oanda_client.py
"""
APEX Scalper — Oanda API Client
=================================
Handles authenticated connections to the Oanda REST API.
Provides candle fetching and account info retrieval.
Used by both the backtest engine (historical data) and live engine (streaming).
"""

import pandas as pd
from datetime import datetime
import oandapyV20
import oandapyV20.endpoints.instruments as instruments
import oandapyV20.endpoints.accounts as accounts

from config.settings import OANDA_ACCOUNT_ID, OANDA_API_KEY, OANDA_ENVIRONMENT
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ── Oanda granularity map: our TF names → Oanda API granularity strings ──
GRANULARITY_MAP = {
    "S5":  "S5",
    "S10": "S10",
    "S15": "S15",
    "S30": "S30",
    "M1":  "M1",
    "M5":  "M5",
    "M15": "M15",
    "M30": "M30",
    "H1":  "H1",
    "H4":  "H4",
    "D":   "D",
    "W":   "W",
}


class OandaClient:
    """
    Wrapper around the oandapyV20 library.
    Instantiate once and reuse across the application.
    """

    def __init__(self):
        """Initialise the Oanda API client using credentials from settings."""
        environment = "live" if OANDA_ENVIRONMENT == "live" else "practice"
        self.client = oandapyV20.API(
            access_token=OANDA_API_KEY,
            environment=environment
        )
        self.account_id = OANDA_ACCOUNT_ID
        logger.info(f"OandaClient initialised — environment: {environment.upper()}")

    # ─────────────────────────────────────────────────────────────────────
    # CANDLE DATA
    # ─────────────────────────────────────────────────────────────────────

    def get_candles(
        self,
        instrument: str,
        granularity: str,
        count: int = None,
        from_date: str = None,
        to_date: str = None,
        price: str = "M"          # "M" = midpoint | "B" = bid | "A" = ask
    ) -> pd.DataFrame:
        """
        Fetch OHLCV candles from Oanda for a given instrument and timeframe.

        Args:
            instrument:  Oanda instrument name e.g. "XAU_USD"
            granularity: Timeframe string e.g. "M5", "M15", "H1"
            count:       Number of candles to fetch (max 5000 per request)
            from_date:   Start date string "YYYY-MM-DD" (alternative to count)
            to_date:     End date string "YYYY-MM-DD"
            price:       Price type — "M" midpoint, "B" bid, "A" ask

        Returns:
            pd.DataFrame with columns: [open, high, low, close, volume, complete]
            Index: datetime (UTC)
        """
        gran = GRANULARITY_MAP.get(granularity)
        if gran is None:
            raise ValueError(f"Unsupported granularity: {granularity}")

        # Build request parameters
        params = {"granularity": gran, "price": price}

        if count is not None:
            params["count"] = min(count, 5000)   # Oanda hard limit is 5000
        elif from_date and to_date:
            # Convert date strings to RFC3339 format required by Oanda
            params["from"] = f"{from_date}T00:00:00Z"
            params["to"]   = f"{to_date}T23:59:59Z"
        else:
            raise ValueError("Provide either 'count' or both 'from_date' and 'to_date'.")

        logger.debug(f"Fetching {granularity} candles for {instrument} | params: {params}")

        # Fire the API request
        req = instruments.InstrumentsCandles(instrument=instrument, params=params)
        self.client.request(req)
        raw = req.response.get("candles", [])

        if not raw:
            logger.warning(f"No candles returned for {instrument} {granularity}")
            return pd.DataFrame()

        # Parse the response into a clean DataFrame
        rows = []
        for candle in raw:
            mid = candle.get("mid", {})
            rows.append({
                "time":     candle["time"][:19],        # Trim microseconds
                "open":     float(mid.get("o", 0)),
                "high":     float(mid.get("h", 0)),
                "low":      float(mid.get("l", 0)),
                "close":    float(mid.get("c", 0)),
                "volume":   int(candle.get("volume", 0)),
                "complete": candle.get("complete", True),
            })

        df = pd.DataFrame(rows)
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df.set_index("time", inplace=True)
        df.sort_index(inplace=True)

        # Drop incomplete (live) candles — only use closed candles for signals
        df = df[df["complete"] == True].drop(columns=["complete"])

        logger.debug(f"Fetched {len(df)} {granularity} candles for {instrument}")
        return df

    def get_candles_paginated(
            self,
            instrument: str,
            granularity: str,
            from_date: str,
            to_date: str
    ) -> pd.DataFrame:
        """
        Fetch a long date range by paginating through Oanda's 5000-candle limit.
        Uses count=5000 + advancing 'from' timestamp on each page.
        Merges all pages into a single sorted DataFrame.

        Args:
            instrument:  Oanda symbol
            granularity: Timeframe string
            from_date:   Start date "YYYY-MM-DD"
            to_date:     End date "YYYY-MM-DD"

        Returns:
            Combined pd.DataFrame across the full date range.
        """
        logger.info(f"Paginated fetch: {instrument} {granularity} | {from_date} → {to_date}")

        gran = GRANULARITY_MAP.get(granularity)
        if gran is None:
            raise ValueError(f"Unsupported granularity: {granularity}")

        to_dt = pd.Timestamp(f"{to_date}T23:59:59Z", tz="UTC")
        current_from = f"{from_date}T00:00:00Z"
        all_frames = []
        page = 0

        while True:
            page += 1
            params = {
                "granularity": gran,
                "price": "M",
                "count": 5000,
                "from": current_from,
            }

            logger.debug(f"  Page {page}: fetching from {current_from}")

            try:
                req = instruments.InstrumentsCandles(instrument=instrument, params=params)
                self.client.request(req)
                raw = req.response.get("candles", [])
            except Exception as e:
                logger.error(f"Paginated fetch error on page {page}: {e}")
                break

            if not raw:
                logger.debug(f"  Page {page}: no candles returned — stopping.")
                break

            # Parse into DataFrame
            rows = []
            for candle in raw:
                mid = candle.get("mid", {})
                rows.append({
                    "time": candle["time"][:19],
                    "open": float(mid.get("o", 0)),
                    "high": float(mid.get("h", 0)),
                    "low": float(mid.get("l", 0)),
                    "close": float(mid.get("c", 0)),
                    "volume": int(candle.get("volume", 0)),
                    "complete": candle.get("complete", True),
                })

            df_chunk = pd.DataFrame(rows)
            df_chunk["time"] = pd.to_datetime(df_chunk["time"], utc=True)
            df_chunk.set_index("time", inplace=True)
            df_chunk.sort_index(inplace=True)

            # Drop incomplete candles
            df_chunk = df_chunk[df_chunk["complete"] == True].drop(columns=["complete"])

            if df_chunk.empty:
                break

            # Only keep candles within the requested date range
            df_chunk = df_chunk[df_chunk.index <= to_dt]
            if not df_chunk.empty:
                all_frames.append(df_chunk)

            last_ts = df_chunk.index[-1]
            logger.debug(f"  Page {page}: {len(df_chunk)} candles | last: {last_ts}")

            # Stop if we've reached or passed the end date
            if last_ts >= to_dt:
                break

            # Stop if we got fewer than 5000 candles (means we hit the end)
            if len(raw) < 5000:
                break

            # Advance from timestamp by 1 period to avoid re-fetching the last candle
            current_from = (last_ts + pd.Timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        if not all_frames:
            logger.warning(f"No data collected for {instrument} {granularity}")
            return pd.DataFrame()

        combined = pd.concat(all_frames)
        combined = combined[~combined.index.duplicated(keep="last")]
        combined.sort_index(inplace=True)

        logger.info(
            f"Paginated fetch complete: {instrument} {granularity} | "
            f"{page} pages | {len(combined)} total candles"
        )
        return combined

    # ─────────────────────────────────────────────────────────────────────
    # ACCOUNT INFO
    # ─────────────────────────────────────────────────────────────────────

    def get_account_summary(self) -> dict:
        """
        Fetch current account balance, NAV, margin used, and open trade count.

        Returns:
            dict with keys: balance, nav, margin_used, open_trade_count
        """
        req = accounts.AccountSummary(self.account_id)
        self.client.request(req)
        summary = req.response.get("account", {})

        return {
            "balance":          float(summary.get("balance", 0)),
            "nav":              float(summary.get("NAV", 0)),
            "margin_used":      float(summary.get("marginUsed", 0)),
            "open_trade_count": int(summary.get("openTradeCount", 0)),
        }