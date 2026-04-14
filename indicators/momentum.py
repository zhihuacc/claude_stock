import pandas as pd
import pandas_ta as ta
from .base import BaseIndicator

class MomentumIndicators(BaseIndicator):
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        self.validate_input(df, min_rows=1)
        df = df.copy()
        price = self._ensure_price_col(df)

        cfg = self.config.get("indicators", {}).get("momentum", {})

        # RSI
        rsi_period = cfg.get("rsi_period", 14)
        df[f"RSI_{rsi_period}"] = ta.rsi(price, length=rsi_period)

        # Stochastic
        stoch_cfg = cfg.get("stochastic", {"k_period": 14, "d_period": 3, "smooth_k": 3})
        k, d, smooth = stoch_cfg["k_period"], stoch_cfg["d_period"], stoch_cfg["smooth_k"]
        stoch_df = ta.stoch(df["high"], df["low"], price, k=k, d=d, smooth_k=smooth)
        if stoch_df is not None and not stoch_df.empty:
            df["STOCH_K"] = stoch_df.iloc[:, 0]
            df["STOCH_D"] = stoch_df.iloc[:, 1]

        # ROC
        roc_period = cfg.get("roc_period", 12)
        df[f"ROC_{roc_period}"] = ta.roc(price, length=roc_period)

        # Williams %R
        willr_period = cfg.get("williams_r_period", 14)
        df[f"WILLR_{willr_period}"] = ta.willr(df["high"], df["low"], price, length=willr_period)

        return df
