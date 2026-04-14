import pandas as pd
import pandas_ta as ta
from .base import BaseIndicator

class VolumeIndicators(BaseIndicator):
    def calculate(self, df: pd.DataFrame, timeframe: str = "1D") -> pd.DataFrame:
        self.validate_input(df, min_rows=1)
        df = df.copy()
        price = self._ensure_price_col(df)

        cfg = self.config.get("indicators", {}).get("volume", {})

        # OBV
        if cfg.get("obv", True):
            df["OBV"] = ta.obv(price, df["volume"])

        # Volume SMA and ratio
        vol_period = cfg.get("volume_sma_period", 20)
        df[f"VOL_SMA_{vol_period}"] = ta.sma(df["volume"].astype(float), length=vol_period)
        df["VOL_RATIO"] = df["volume"] / df[f"VOL_SMA_{vol_period}"]

        # VWAP — only for 1H and 1D
        if cfg.get("vwap", True) and timeframe in ("1H", "1D"):
            # pandas_ta vwap needs DatetimeIndex
            if "datetime" in df.columns:
                tmp = df.set_index("datetime")
            else:
                tmp = df.copy()
            vwap_series = ta.vwap(tmp["high"], tmp["low"], tmp["close"], tmp["volume"])
            if vwap_series is not None:
                if "datetime" in df.columns:
                    df["VWAP"] = vwap_series.values
                else:
                    df["VWAP"] = vwap_series
        else:
            df["VWAP"] = None

        return df
