import pandas as pd
import pandas_ta as ta
from .base import BaseIndicator

class VolatilityIndicators(BaseIndicator):
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        self.validate_input(df, min_rows=1)
        df = df.copy()
        price = self._ensure_price_col(df)

        cfg = self.config.get("indicators", {}).get("volatility", {})

        # Bollinger Bands
        bb_cfg = cfg.get("bollinger_bands", {"period": 20, "std_dev": 2.0})
        period, std = bb_cfg["period"], bb_cfg["std_dev"]
        bb_df = ta.bbands(price, length=period, std=std)
        if bb_df is not None and not bb_df.empty:
            # pandas_ta columns: BBL_20_2.0, BBM_20_2.0, BBU_20_2.0, BBB_20_2.0, BBP_20_2.0
            df["BB_LOWER"]  = bb_df.iloc[:, 0]
            df["BB_MIDDLE"] = bb_df.iloc[:, 1]
            df["BB_UPPER"]  = bb_df.iloc[:, 2]
            df["BB_WIDTH"]  = bb_df.iloc[:, 3]  # BBB = bandwidth
            df["BB_PCT_B"]  = bb_df.iloc[:, 4]  # BBP = %B

        # ATR
        atr_period = cfg.get("atr_period", 14)
        atr_series = ta.atr(df["high"], df["low"], price, length=atr_period)
        if atr_series is not None:
            df[f"ATR_{atr_period}"] = atr_series

        # Keltner Channel
        kc_cfg = cfg.get("keltner_channel", {"ema_period": 20, "atr_period": 10, "multiplier": 2.0})
        kc_df = ta.kc(df["high"], df["low"], price,
                      length=kc_cfg["ema_period"],
                      scalar=kc_cfg["multiplier"],
                      atr_length=kc_cfg["atr_period"])
        if kc_df is not None and not kc_df.empty:
            df["KC_LOWER"]  = kc_df.iloc[:, 0]
            df["KC_MIDDLE"] = kc_df.iloc[:, 1]
            df["KC_UPPER"]  = kc_df.iloc[:, 2]

        return df
