import logging
import pandas as pd
from datetime import datetime
from data.storage import StorageManager
from indicators.trend import TrendIndicators
from indicators.momentum import MomentumIndicators
from indicators.volatility import VolatilityIndicators
from indicators.volume import VolumeIndicators
from indicators.support_resistance import SupportResistanceIndicators
from .rules import ALL_RULES

logger = logging.getLogger(__name__)


class IndicatorRunner:
    """Runs all indicator calculations on stored OHLCV and saves results."""

    def __init__(self, storage: StorageManager, config: dict):
        self.storage = storage
        self.config = config
        self.calculators = {
            "trend": TrendIndicators(config),
            "momentum": MomentumIndicators(config),
            "volatility": VolatilityIndicators(config),
            "volume": VolumeIndicators(config),
            "support_resistance": SupportResistanceIndicators(config),
        }

    def run(self, symbols=None, timeframes=None, categories=None, recalculate=False, dry_run=False):
        watchlist = [e["symbol"] for e in self.config["watchlist"]]
        symbols = symbols or watchlist
        timeframes = timeframes or self.config["data"]["timeframes"]
        categories = categories or list(self.calculators.keys())
        total = 0
        for symbol in symbols:
            for tf in timeframes:
                n = self._run_one(symbol, tf, categories, recalculate, dry_run)
                total += n
        logger.info(f"Indicators: wrote {total} rows total")
        return total

    def _run_one(self, symbol, timeframe, categories, recalculate, dry_run) -> int:
        df = self.storage.get_ohlcv(symbol, timeframe)
        if df.empty:
            logger.warning(f"{symbol} {timeframe}: no OHLCV data, skipping indicators")
            return 0

        df = df.sort_values("datetime").reset_index(drop=True)
        n_rows = len(df)
        logger.info(f"{symbol} {timeframe}: computing indicators on {n_rows} rows")

        for cat in categories:
            calc = self.calculators.get(cat)
            if calc is None:
                continue
            try:
                if cat == "volume":
                    df = calc.calculate(df, timeframe=timeframe)
                else:
                    df = calc.calculate(df)
            except Exception as e:
                logger.error(f"{symbol} {timeframe} {cat}: {e}")

        # Collect indicator columns (everything not in base OHLCV)
        base_cols = {"symbol", "timeframe", "datetime", "open", "high", "low", "close", "volume", "adjusted_close"}
        ind_cols = [c for c in df.columns if c not in base_cols]

        if not ind_cols:
            return 0

        records = []
        for _, row in df.iterrows():
            dt = row["datetime"]
            for col in ind_cols:
                val = row.get(col)
                if pd.isna(val) if val is not None else False:
                    val = None
                records.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "datetime": dt,
                    "indicator_name": col,
                    "value": float(val) if val is not None else None,
                })

        if dry_run:
            logger.info(f"[dry-run] Would write {len(records)} indicator rows for {symbol} {timeframe}")
            return len(records)

        return self.storage.upsert_indicators(records)


class SignalEngine:
    """Evaluates signal rules against stored indicators."""

    def __init__(self, storage: StorageManager, config: dict):
        self.storage = storage
        self.config = config

    def run(self, symbols=None, timeframes=None, dry_run=False) -> list[dict]:
        if not self.config["signals"].get("enabled", True):
            return []
        watchlist = [e["symbol"] for e in self.config["watchlist"]]
        symbols = symbols or watchlist
        timeframes = timeframes or self.config["signals"].get("timeframes", ["1D"])
        all_signals = []
        for symbol in symbols:
            for tf in timeframes:
                signals = self._run_one(symbol, tf, dry_run)
                all_signals.extend(signals)
        return all_signals

    def _run_one(self, symbol, timeframe, dry_run) -> list[dict]:
        # Need last 2 rows for crossover detection
        df_ind = self.storage.get_indicators(symbol, timeframe, limit=2)
        df_ohlcv = self.storage.get_ohlcv(symbol, timeframe, limit=2)

        if df_ind.empty or len(df_ind) == 0:
            logger.debug(f"{symbol} {timeframe}: no indicators, skipping signals")
            return []

        # Sort ascending so row[-1] is latest, row[-2] is prior
        df_ind = df_ind.sort_index()
        df_ohlcv = df_ohlcv.sort_values("datetime")

        # Build indicator dicts including close price for BB breakout rules
        def build_ind_dict(row_series, ohlcv_df, dt):
            d = row_series.dropna().to_dict()
            # attach close price
            match = ohlcv_df[ohlcv_df["datetime"] == dt]
            if not match.empty:
                d["close"] = match.iloc[0]["close"]
            return d

        datetimes = df_ind.index.tolist()
        if len(datetimes) < 1:
            return []

        latest_dt = datetimes[-1]
        cur_ind = build_ind_dict(df_ind.loc[latest_dt], df_ohlcv, latest_dt)
        if len(datetimes) >= 2:
            prev_dt = datetimes[-2]
            prev_ind = build_ind_dict(df_ind.loc[prev_dt], df_ohlcv, prev_dt)
        else:
            prev_ind = {}

        signals = []
        for rule_fn in ALL_RULES:
            try:
                sig = rule_fn(symbol, timeframe, latest_dt, cur_ind, prev_ind, self.config)
                if sig:
                    signals.append(sig)
            except Exception as e:
                logger.debug(f"Rule {rule_fn.__name__} error for {symbol} {timeframe}: {e}")

        if not dry_run and signals:
            self.storage.upsert_signals(signals)
            logger.info(f"{symbol} {timeframe}: {len(signals)} signal(s) triggered")

        return signals
