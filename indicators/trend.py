import pandas as pd
import pandas_ta as ta
from .base import BaseIndicator

class TrendIndicators(BaseIndicator):
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        self.validate_input(df, min_rows=1)
        df = df.copy()
        price = self._ensure_price_col(df)

        cfg = self.config.get("indicators", {}).get("trend", {})

        # SMA
        for period in cfg.get("sma_periods", [20, 50, 200]):
            df[f"SMA_{period}"] = ta.sma(price, length=period)

        # EMA
        for period in cfg.get("ema_periods", [9, 21]):
            df[f"EMA_{period}"] = ta.ema(price, length=period)

        # MACD
        macd_cfg = cfg.get("macd", {"fast": 12, "slow": 26, "signal": 9})
        fast, slow, sig = macd_cfg["fast"], macd_cfg["slow"], macd_cfg["signal"]
        macd_df = ta.macd(price, fast=fast, slow=slow, signal=sig)
        if macd_df is not None and not macd_df.empty:
            # pandas_ta column names: MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
            cols = macd_df.columns.tolist()
            df["MACD_LINE"]   = macd_df.iloc[:, 0]  # MACD line
            df["MACD_HIST"]   = macd_df.iloc[:, 1]  # histogram
            df["MACD_SIGNAL"] = macd_df.iloc[:, 2]  # signal line

        # ADX
        adx_period = cfg.get("adx_period", 14)
        adx_df = ta.adx(df["high"], df["low"], price, length=adx_period)
        if adx_df is not None and not adx_df.empty:
            df[f"ADX_{adx_period}"]       = adx_df.iloc[:, 0]  # ADX
            df[f"DI_PLUS_{adx_period}"]   = adx_df.iloc[:, 1]  # DMP
            df[f"DI_MINUS_{adx_period}"]  = adx_df.iloc[:, 2]  # DMN

        return df
