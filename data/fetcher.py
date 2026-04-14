import logging
import time
from datetime import datetime, timedelta, date
from typing import Optional
import pandas as pd
import yfinance as yf
from .storage import StorageManager

logger = logging.getLogger(__name__)

TIMEFRAME_MAP = {
    "1H": "1h",
    "1D": "1d",
    "1W": "1wk",
    "1M": "1mo",
}


class YFinanceFetcher:
    def __init__(self, storage: StorageManager, config: dict):
        self.storage = storage
        self.config = config

    def fetch_all(self, symbols=None, timeframes=None, force=False, since=None, dry_run=False):
        """Fetch OHLCV for all symbols+timeframes. Returns dict of {(symbol,tf): rows_written}."""
        cfg = self.config["data"]
        watchlist = [e["symbol"] for e in self.config["watchlist"]]
        symbols = symbols or watchlist
        timeframes = timeframes or cfg["timeframes"]
        results = {}
        for symbol in symbols:
            for tf in timeframes:
                try:
                    n = self._fetch_one(symbol, tf, force=force, since=since, dry_run=dry_run)
                    results[(symbol, tf)] = n
                except Exception as e:
                    logger.error(f"Failed to fetch {symbol} {tf}: {e}")
                    results[(symbol, tf)] = 0
        return results

    def _fetch_one(self, symbol: str, timeframe: str, force=False, since=None, dry_run=False) -> int:
        cfg = self.config["data"]
        interval = TIMEFRAME_MAP[timeframe]

        # Determine start date
        if since:
            start = pd.Timestamp(since)
        elif force:
            days = cfg.get("initial_history_hours", 60) if timeframe == "1H" else cfg.get("initial_history_days", 730)
            start = pd.Timestamp.now() - timedelta(days=days)
        else:
            last_dt = self.storage.get_last_fetch_datetime(symbol, timeframe)
            if last_dt is None:
                days = cfg.get("initial_history_hours", 60) if timeframe == "1H" else cfg.get("initial_history_days", 730)
                start = pd.Timestamp.now() - timedelta(days=days)
            else:
                # advance by one period
                if timeframe == "1H":
                    start = pd.Timestamp(last_dt) + timedelta(hours=1)
                else:
                    start = pd.Timestamp(last_dt) + timedelta(days=1)

        end = pd.Timestamp.now()

        if start >= end:
            logger.info(f"{symbol} {timeframe}: already up to date")
            return 0

        logger.info(f"Fetching {symbol} {timeframe} from {start.date()} ...")
        df = self._download_with_retry(symbol, interval, start, end)

        if df is None or df.empty:
            logger.info(f"{symbol} {timeframe}: no data returned (holiday/weekend/off-hours)")
            return 0

        df = self._normalize(df, symbol, timeframe)
        if df.empty:
            return 0

        if dry_run:
            logger.info(f"[dry-run] Would write {len(df)} rows for {symbol} {timeframe}")
            return len(df)

        records = df.to_dict("records")
        n = self.storage.upsert_ohlcv(records)
        last_dt = df["datetime"].max()
        self.storage.update_fetch_log(symbol, timeframe, last_dt)
        logger.info(f"{symbol} {timeframe}: wrote {n} rows, last bar {last_dt}")
        return n

    def _download_with_retry(self, symbol: str, interval: str, start, end, max_retries=3) -> Optional[pd.DataFrame]:
        for attempt in range(max_retries):
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(interval=interval, start=start, end=end, auto_adjust=False, actions=False)
                return df
            except Exception as e:
                wait = 2 ** attempt
                logger.warning(f"Download failed for {symbol} (attempt {attempt+1}/{max_retries}): {e}. Retrying in {wait}s...")
                time.sleep(wait)
        logger.error(f"All retries exhausted for {symbol}")
        return None

    def _normalize(self, df: pd.DataFrame, symbol: str, timeframe: str) -> pd.DataFrame:
        """Normalize yfinance output to standard column set."""
        if df.empty:
            return df

        # yfinance returns tz-aware index; strip tz
        df.index = df.index.tz_localize(None) if df.index.tz is None else df.index.tz_convert("America/New_York").tz_localize(None)

        rename = {}
        for col in df.columns:
            cl = col.lower()
            if cl == "open":
                rename[col] = "open"
            elif cl == "high":
                rename[col] = "high"
            elif cl == "low":
                rename[col] = "low"
            elif cl == "close":
                rename[col] = "close"
            elif cl == "volume":
                rename[col] = "volume"
            elif cl in ("adj close", "adjclose", "adjusted close"):
                rename[col] = "adjusted_close"
        df = df.rename(columns=rename)

        keep = [c for c in ["open", "high", "low", "close", "volume", "adjusted_close"] if c in df.columns]
        df = df[keep].copy()

        if "adjusted_close" not in df.columns:
            df["adjusted_close"] = None  # 1H: yfinance may not provide it

        df.index.name = "datetime"
        df = df.reset_index()
        df["symbol"] = symbol
        df["timeframe"] = timeframe
        df = df.dropna(subset=["open", "high", "low", "close"])
        df["volume"] = df["volume"].fillna(0).astype(int)
        return df
