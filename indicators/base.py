from abc import ABC, abstractmethod
import pandas as pd

REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]

class BaseIndicator(ABC):
    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Input: OHLCV DataFrame with columns [open, high, low, close, volume],
               DatetimeIndex or 'datetime' column.
        Output: same DataFrame with indicator columns appended.
        Warmup rows produce NaN, which callers store as NULL.
        """
        pass

    def validate_input(self, df: pd.DataFrame, min_rows: int = 1) -> None:
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        if len(df) < min_rows:
            raise ValueError(f"Need at least {min_rows} rows, got {len(df)}")

    def _ensure_price_col(self, df: pd.DataFrame) -> pd.Series:
        """Return adjusted_close if available and non-null, else close."""
        if "adjusted_close" in df.columns and df["adjusted_close"].notna().any():
            return df["adjusted_close"].fillna(df["close"])
        return df["close"]
