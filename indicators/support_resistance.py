import pandas as pd
import numpy as np
from .base import BaseIndicator

class SupportResistanceIndicators(BaseIndicator):
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        self.validate_input(df, min_rows=2)
        df = df.copy()
        price = self._ensure_price_col(df)

        cfg = self.config.get("indicators", {}).get("support_resistance", {})
        pivot_type = cfg.get("pivot_type", "standard")
        weeks = cfg.get("week_high_low_periods", 52)

        # Pivot Points — use prior bar's H/L/C
        prev_high  = df["high"].shift(1)
        prev_low   = df["low"].shift(1)
        prev_close = price.shift(1)

        if pivot_type == "standard":
            pp = (prev_high + prev_low + prev_close) / 3
            df["PP"] = pp
            df["R1"] = 2 * pp - prev_low
            df["R2"] = pp + (prev_high - prev_low)
            df["R3"] = prev_high + 2 * (pp - prev_low)
            df["S1"] = 2 * pp - prev_high
            df["S2"] = pp - (prev_high - prev_low)
            df["S3"] = prev_low - 2 * (prev_high - pp)
        elif pivot_type == "fibonacci":
            pp = (prev_high + prev_low + prev_close) / 3
            rng = prev_high - prev_low
            df["PP"] = pp
            df["R1"] = pp + 0.382 * rng
            df["R2"] = pp + 0.618 * rng
            df["R3"] = pp + 1.000 * rng
            df["S1"] = pp - 0.382 * rng
            df["S2"] = pp - 0.618 * rng
            df["S3"] = pp - 1.000 * rng
        else:  # woodie
            pp = (prev_high + prev_low + 2 * df["close"].shift(1)) / 4
            df["PP"] = pp
            df["R1"] = 2 * pp - prev_low
            df["R2"] = pp + prev_high - prev_low
            df["R3"] = prev_high + 2 * (pp - prev_low)
            df["S1"] = 2 * pp - prev_high
            df["S2"] = pp - prev_high + prev_low
            df["S3"] = prev_low - 2 * (prev_high - pp)

        # 52-week high/low (rolling window)
        window = weeks * 5  # approximate trading days in 52 weeks
        df["HIGH_52W"] = df["high"].rolling(window=window, min_periods=1).max()
        df["LOW_52W"]  = df["low"].rolling(window=window, min_periods=1).min()

        df["PCT_FROM_52W_HIGH"] = ((df["HIGH_52W"] - price) / df["HIGH_52W"] * 100).round(4)
        df["PCT_FROM_52W_LOW"]  = ((price - df["LOW_52W"]) / df["LOW_52W"] * 100).round(4)

        return df
